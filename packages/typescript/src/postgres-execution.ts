import { randomUUID } from 'node:crypto';
import type pg from 'pg';
import {
  AgentEvent,
  DefaultExecutionEventBus,
  DefaultExecutionEventBusManager,
  type AgentExecutionEvent,
  type ExecutionEventBusManager,
  ServerCallContext,
  type TaskStore,
} from '@a2a-js/sdk/server';
import { TaskState, type Task } from '@a2a-js/sdk';
import { TaskNotFoundError, TaskNotCancelableError } from '@a2a-js/sdk/errors';

export const EXECUTION_FENCE = 'a2a-lite.execution-fence';
export const CANCEL_TASK = 'a2a-lite.cancel-task';
export const PERSISTED_CANCEL = 'a2a-lite.persisted-cancel';
export const RECOVER_EXPIRED = 'a2a-lite.recover-expired';
export const CANCEL_OBSERVER = 'a2a-lite.cancel-observer';
export interface DistributedExecutionOptions {
  leaseMs?: number;
  pollIntervalMs?: number;
}
export interface ExecutionLease {
  readonly signal: AbortSignal;
  readonly checkpointData: unknown;
  checkpoint(data: unknown): Promise<void>;
  release(): Promise<void>;
}
/** Explicit opt-in checkpoint SPI. Arbitrary JavaScript skills are never restarted automatically. */
export interface DistributedExecution {
  readonly eventBusManager: ExecutionEventBusManager;
  acquire(taskId: string, context: ServerCallContext): Promise<ExecutionLease>;
  cancelTask(taskId: string, context: ServerCallContext): Promise<Task>;
  reconcileExpiredTasks(): Promise<number>;
}

export class PostgresExecution implements DistributedExecution {
  readonly eventBusManager: ExecutionEventBusManager;
  private readonly local = new DefaultExecutionEventBusManager();
  private readonly remote = new Set<PollingTaskBus>();
  private readonly leases = new Set<ExecutionLease>();
  private readonly leaseMs: number;
  private readonly pollMs: number;
  private recoveryTimer?: ReturnType<typeof setTimeout>;
  private recoveryRunning?: Promise<unknown>;
  private closed = false;
  constructor(
    private readonly pool: pg.Pool,
    private readonly store: TaskStore,
    private readonly prefix: string,
    options: DistributedExecutionOptions = {},
    private readonly taskTable = 'tasks',
  ) {
    this.leaseMs = options.leaseMs ?? 15000;
    this.pollMs = options.pollIntervalMs ?? 250;
    if (
      !Number.isSafeInteger(this.leaseMs) ||
      this.leaseMs < 300 ||
      !Number.isSafeInteger(this.pollMs) ||
      this.pollMs < 10 ||
      this.pollMs >= this.leaseMs / 2
    )
      throw new Error('Invalid execution lease/poll interval');
    this.eventBusManager = {
      createOrGetByTaskId: (id, context) => this.local.createOrGetByTaskId(id, context),
      getByTaskId: (id, context) => {
        const existing = this.local.getByTaskId(id, context);
        if (existing || !context) return existing;
        const bus = new PollingTaskBus(pool, prefix, id, context, this.pollMs, () => this.remote.delete(bus));
        this.remote.add(bus);
        return bus;
      },
      cleanupByTaskId: (id, context) => this.local.cleanupByTaskId(id, context),
    };
  }
  start(): void {
    const tick = async () => {
      if (this.closed) return;
      this.recoveryRunning = this.reconcileExpiredTasks().catch(() => {});
      await this.recoveryRunning;
      if (!this.closed) {
        this.recoveryTimer = setTimeout(() => {
          void tick();
        }, this.pollMs);
        this.recoveryTimer.unref();
      }
    };
    void tick();
  }
  async reconcileExpiredTasks(): Promise<number> {
    const candidates = await this.pool.query(
      `SELECT l.tenant,l.owner,l.task_id,l.fence,l.checkpoint,now() AS observed_at FROM ${this.prefix}_leases l JOIN ${this.taskTable} t ON t.tenant=l.tenant AND t.owner=l.owner AND t.id=l.task_id WHERE l.lease_until<now() AND NOT l.cancel_requested AND t.status_state IN ('TASK_STATE_SUBMITTED','TASK_STATE_WORKING') ORDER BY l.lease_until LIMIT 64`,
    );
    let recovered = 0;
    for (const row of candidates.rows) {
      const context = new ServerCallContext({
        tenant: row.tenant,
        user: { userName: row.owner, isAuthenticated: true },
      });
      const task = await this.store.load(row.task_id, context);
      if (!task || ![TaskState.TASK_STATE_SUBMITTED, TaskState.TASK_STATE_WORKING].includes(task.status!.state))
        continue;
      context.state.set(RECOVER_EXPIRED, Number(row.fence));
      try {
        await this.store.save(
          {
            ...task,
            status: {
              state: row.checkpoint === null ? TaskState.TASK_STATE_FAILED : TaskState.TASK_STATE_INPUT_REQUIRED,
              timestamp: row.observed_at.toISOString(),
              message: undefined,
            },
          },
          context,
        );
        recovered++;
      } catch {
        /* A renewed/replaced lease or a concurrent terminal state wins. */
      }
    }
    return recovered;
  }
  async acquire(taskId: string, context: ServerCallContext): Promise<ExecutionLease> {
    const holder = randomUUID();
    const tenant = context.tenant ?? '';
    const owner = context.user?.userName ?? '';
    const result = await this.pool.query(
      `INSERT INTO ${this.prefix}_leases (tenant,owner,task_id,holder,fence,lease_until,cancel_requested) VALUES ($1,$2,$3,$4,1,now()+($5 * interval '1 millisecond'),false) ON CONFLICT (tenant,owner,task_id) DO UPDATE SET holder=$4,fence=${this.prefix}_leases.fence+1,lease_until=now()+($5 * interval '1 millisecond'),cancel_requested=false WHERE ${this.prefix}_leases.lease_until<now() RETURNING fence,checkpoint`,
      [tenant, owner, taskId, holder, this.leaseMs],
    );
    const row = result.rows[0];
    if (!row) throw new Error('Task execution is already owned by another worker');
    const fence = Number(row.fence);
    context.state.set(EXECUTION_FENCE, { holder, fence });
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    let released = false;
    const renew = async () => {
      if (released) return;
      try {
        const renewed = await this.pool.query(
          `UPDATE ${this.prefix}_leases SET lease_until=now()+($1 * interval '1 millisecond') WHERE tenant=$2 AND owner=$3 AND task_id=$4 AND holder=$5 AND fence=$6 AND lease_until>now() AND NOT cancel_requested RETURNING fence`,
          [this.leaseMs, tenant, owner, taskId, holder, fence],
        );
        if (!renewed.rowCount) {
          const current = await this.pool.query(
            `SELECT cancel_requested FROM ${this.prefix}_leases WHERE tenant=$1 AND owner=$2 AND task_id=$3`,
            [tenant, owner, taskId],
          );
          const error = new Error(current.rows[0]?.cancel_requested ? 'Task canceled' : 'Task execution lease lost');
          if (current.rows[0]?.cancel_requested) error.name = 'TaskCanceledError';
          controller.abort(error);
          released = true;
          this.leases.delete(lease);
          return;
        }
      } catch {
        controller.abort(new Error('Task execution lease unavailable'));
        return;
      }
      if (!released) {
        timer = setTimeout(() => {
          void renew();
        }, this.pollMs);
        timer.unref();
      }
    };
    timer = setTimeout(() => {
      void renew();
    }, this.pollMs);
    timer.unref();
    const lease: ExecutionLease = {
      signal: controller.signal,
      checkpointData: row.checkpoint,
      checkpoint: async (data) => {
        controller.signal.throwIfAborted();
        const encoded = JSON.stringify(data);
        if (encoded === undefined || Buffer.byteLength(encoded) > 65536)
          throw new Error('Checkpoint must be JSON of at most 64KiB');
        const saved = await this.pool.query(
          `UPDATE ${this.prefix}_leases SET checkpoint=$1::jsonb WHERE tenant=$2 AND owner=$3 AND task_id=$4 AND holder=$5 AND fence=$6 AND lease_until>now() AND NOT cancel_requested`,
          [encoded, tenant, owner, taskId, holder, fence],
        );
        if (!saved.rowCount) throw new Error('Execution lease no longer owns the checkpoint');
      },
      release: async () => {
        if (released) return;
        released = true;
        clearTimeout(timer);
        this.leases.delete(lease);
        await this.pool.query(
          `UPDATE ${this.prefix}_leases SET lease_until=now() WHERE tenant=$1 AND owner=$2 AND task_id=$3 AND holder=$4 AND fence=$5`,
          [tenant, owner, taskId, holder, fence],
        );
      },
    };
    this.leases.add(lease);
    return lease;
  }
  async cancelTask(taskId: string, context: ServerCallContext): Promise<Task> {
    for (let attempt = 0; attempt < 3; attempt++) {
      const task = await this.store.load(taskId, context);
      if (!task) throw new TaskNotFoundError();
      if (task.status?.state === TaskState.TASK_STATE_CANCELED) return task;
      if (
        task.status &&
        [TaskState.TASK_STATE_COMPLETED, TaskState.TASK_STATE_FAILED, TaskState.TASK_STATE_REJECTED].includes(
          task.status.state,
        )
      )
        throw new TaskNotCancelableError();
      const canceled = {
        ...task,
        status: { state: TaskState.TASK_STATE_CANCELED, timestamp: new Date().toISOString(), message: undefined },
      };
      context.state.set(CANCEL_TASK, true);
      try {
        await this.store.save(canceled, context);
        return canceled;
      } catch (error) {
        if (attempt === 2 || !(error instanceof Error) || !error.message.includes('Concurrent task update'))
          throw error;
      } finally {
        context.state.delete(CANCEL_TASK);
      }
    }
    throw new TaskNotCancelableError();
  }
  async close(): Promise<void> {
    this.closed = true;
    clearTimeout(this.recoveryTimer);
    await this.recoveryRunning;
    for (const bus of this.remote) bus.close();
    await Promise.allSettled([...this.leases].map((lease) => lease.release()));
  }
}

/** Poll a bounded per-task journal; the initial Task snapshot remains owned by the SDK. */
class PollingTaskBus extends DefaultExecutionEventBus {
  private stopped = false;
  private timer?: ReturnType<typeof setTimeout>;
  private cursor?: number;
  constructor(
    private readonly pool: pg.Pool,
    private readonly prefix: string,
    private readonly taskId: string,
    private readonly context: ServerCallContext,
    private readonly pollMs: number,
    private readonly onClose: () => void,
  ) {
    super();
    void this.poll();
  }
  override off(name: 'event', listener: (event: AgentExecutionEvent) => void): this;
  override off(name: 'finished', listener: () => void): this;
  override off(name: 'event' | 'finished', listener: ((event: AgentExecutionEvent) => void) | (() => void)): this {
    if (name === 'event') {
      super.off(name, listener as (event: AgentExecutionEvent) => void);
      this.close();
    } else super.off(name, listener as () => void);
    return this;
  }
  close(): void {
    if (this.stopped) return;
    this.stopped = true;
    clearTimeout(this.timer);
    this.finished();
    this.onClose();
  }
  private async poll(): Promise<void> {
    if (this.stopped) return;
    try {
      const scope = [this.context.tenant ?? '', this.context.user?.userName ?? '', this.taskId];
      // The initial SDK snapshot may have raced a committed terminal event.
      // Replay the latest journal snapshot first instead of skipping to its revision.
      const result =
        this.cursor === undefined
          ? await this.pool.query(
              `SELECT revision,task_data FROM ${this.prefix}_journal WHERE tenant=$1 AND owner=$2 AND task_id=$3 ORDER BY revision DESC LIMIT 1`,
              scope,
            )
          : await this.pool.query(
              `SELECT revision,task_data FROM ${this.prefix}_journal WHERE tenant=$1 AND owner=$2 AND task_id=$3 AND revision>$4 ORDER BY revision LIMIT 16`,
              [...scope, this.cursor],
            );
      this.cursor ??= 0;
      for (const row of result.rows) {
        if (this.stopped) break;
        this.cursor = Number(row.revision);
        const task = row.task_data as Task;
        this.publish(AgentEvent.task(task));
        if (task.status)
          this.publish(
            AgentEvent.statusUpdate({
              taskId: task.id,
              contextId: task.contextId,
              status: task.status,
              metadata: { revision: this.cursor },
            }),
          );
        if (
          task.status &&
          [
            TaskState.TASK_STATE_COMPLETED,
            TaskState.TASK_STATE_FAILED,
            TaskState.TASK_STATE_CANCELED,
            TaskState.TASK_STATE_REJECTED,
            TaskState.TASK_STATE_INPUT_REQUIRED,
          ].includes(task.status.state)
        ) {
          this.close();
          return;
        }
      }
    } catch {
      this.close();
      return;
    }
    if (!this.stopped) {
      this.timer = setTimeout(() => {
        void this.poll();
      }, this.pollMs);
      this.timer.unref();
    }
  }
}
