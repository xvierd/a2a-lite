/** Boundary tests; PostgreSQL transaction semantics remain in the real database suite. */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type pg from 'pg';
import { TaskState, type Task } from '@a2a-js/sdk';
import {
  DefaultExecutionEventBus,
  ServerCallContext,
  type AgentExecutionEvent,
  type RequestContext,
  type TaskStore,
} from '@a2a-js/sdk/server';
import { TaskNotCancelableError, TaskNotFoundError } from '@a2a-js/sdk/errors';
import { LiteAgentExecutor } from '../src/executor.js';
import { CANCEL_TASK, EXECUTION_FENCE, PostgresExecution, RECOVER_EXPIRED } from '../src/postgres-execution.js';
import type { SkillDefinition } from '../src/types.js';

function task(id = 'task', state = TaskState.TASK_STATE_WORKING): Task {
  return {
    id,
    contextId: 'conversation',
    status: { state, timestamp: '2026-10-17T12:00:00Z', message: undefined },
    history: [],
    artifacts: [],
    metadata: undefined,
  };
}

function context(): ServerCallContext {
  return new ServerCallContext({ tenant: 'tenant-a', user: { userName: 'alice', isAuthenticated: true } });
}

function result(rows: Record<string, unknown>[] = [], rowCount = rows.length) {
  return { rows, rowCount };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

const coordinators: PostgresExecution[] = [];
function fixture(options = { leaseMs: 1000, pollIntervalMs: 50 }) {
  // Script results/failures at the pg boundary; this does not interpret SQL.
  const query = vi.fn(async (_statement: string, _parameters?: unknown[]) => result());
  const load = vi.fn(async (_id: string, _context: ServerCallContext): Promise<Task | undefined> => undefined);
  const save = vi.fn(async (_task: Task, _context: ServerCallContext) => {});
  const coordinator = new PostgresExecution(
    { query } as unknown as pg.Pool,
    { load, save } as unknown as TaskStore,
    'unit',
    options,
  );
  coordinators.push(coordinator);
  return { query, load, save, coordinator };
}

beforeEach(() => vi.useFakeTimers());
afterEach(async () => {
  await Promise.all(coordinators.splice(0).map((coordinator) => coordinator.close()));
  vi.useRealTimers();
});

describe('execution lease ownership', () => {
  it.each([
    { leaseMs: 299, pollIntervalMs: 50 },
    { leaseMs: 1000.5, pollIntervalMs: 50 },
    { leaseMs: 1000, pollIntervalMs: 9 },
    { leaseMs: 1000, pollIntervalMs: 500 },
  ])('rejects unsafe lease/poll settings %j before using storage', (options) => {
    expect(() => fixture(options)).toThrow('Invalid execution lease/poll interval');
  });

  it('binds a claim to tenant/principal/task and rejects a competing claim', async () => {
    const { coordinator, query } = fixture();
    const ctx = context();
    query.mockResolvedValueOnce(result([{ fence: '7', checkpoint: { next: 3 } }])).mockResolvedValueOnce(result());
    const lease = await coordinator.acquire('task', ctx);
    expect(lease.checkpointData).toEqual({ next: 3 });
    expect(lease.signal.aborted).toBe(false);
    const ownership = ctx.state.get(EXECUTION_FENCE);
    expect(ownership).toEqual({ holder: expect.any(String), fence: 7 });
    expect(query.mock.calls[0][1]).toEqual(['tenant-a', 'alice', 'task', ownership.holder, 1000]);
    const competing = context();
    await expect(coordinator.acquire('task', competing)).rejects.toThrow('already owned');
    expect(competing.state.has(EXECUTION_FENCE)).toBe(false);
    await lease.release();
    const calls = query.mock.calls.length;
    await lease.release();
    await vi.advanceTimersByTimeAsync(5000);
    expect(query).toHaveBeenCalledTimes(calls); // No renewal or double release after relinquishing ownership.
  });

  it('renews the same holder, then aborts when a remote cancellation wins', async () => {
    const { coordinator, query } = fixture();
    query.mockResolvedValueOnce(result([{ fence: 2, checkpoint: null }]));
    const lease = await coordinator.acquire('task', context());
    query.mockResolvedValueOnce(result([{ fence: 2 }], 1));
    await vi.advanceTimersByTimeAsync(50);
    expect(lease.signal.aborted).toBe(false);
    query.mockResolvedValueOnce(result()).mockResolvedValueOnce(result([{ cancel_requested: true }]));
    await vi.advanceTimersByTimeAsync(50);
    expect(lease.signal.reason).toMatchObject({ name: 'TaskCanceledError', message: 'Task canceled' });
    const calls = query.mock.calls.length;
    await expect(lease.checkpoint({ next: 4 })).rejects.toThrow('Task canceled');
    await lease.release();
    await vi.advanceTimersByTimeAsync(1000);
    expect(query).toHaveBeenCalledTimes(calls);
  });

  it.each([[], [{ cancel_requested: false }]])(
    'aborts a lost lease without inventing cancellation %j',
    async (rows) => {
      const { coordinator, query } = fixture();
      query.mockResolvedValueOnce(result([{ fence: 1, checkpoint: null }]));
      const lease = await coordinator.acquire('task', new ServerCallContext());
      expect(query.mock.calls[0][1]?.slice(0, 3)).toEqual(['', '', 'task']);
      query.mockResolvedValueOnce(result()).mockResolvedValueOnce(result(rows));
      await vi.advanceTimersByTimeAsync(50);
      expect(lease.signal.reason).toMatchObject({ name: 'Error', message: 'Task execution lease lost' });
    },
  );

  it('fails closed on renewal outage without exposing the database error', async () => {
    const { coordinator, query } = fixture();
    query.mockResolvedValueOnce(result([{ fence: 1, checkpoint: null }]));
    const lease = await coordinator.acquire('task', context());
    query.mockRejectedValueOnce(new Error('postgres://SECRET@host'));
    await vi.advanceTimersByTimeAsync(50);
    expect(lease.signal.reason.message).toBe('Task execution lease unavailable');
    await expect(lease.checkpoint({ next: 2 })).rejects.toThrow('lease unavailable');
    const count = query.mock.calls.length;
    await vi.advanceTimersByTimeAsync(1000);
    expect(query).toHaveBeenCalledTimes(count);
  });

  it('validates checkpoints before storage and refuses a lost fencing token', async () => {
    const { coordinator, query } = fixture();
    query.mockResolvedValueOnce(result([{ fence: 9, checkpoint: null }]));
    const ctx = context();
    const lease = await coordinator.acquire('task', ctx);
    await expect(lease.checkpoint(undefined)).rejects.toThrow('Checkpoint must be JSON');
    await expect(lease.checkpoint({ large: 'x'.repeat(65536) })).rejects.toThrow('64KiB');
    const circular: { self?: unknown } = {};
    circular.self = circular;
    await expect(lease.checkpoint(circular)).rejects.toThrow();
    expect(query).toHaveBeenCalledOnce();
    query.mockResolvedValueOnce(result([], 1));
    await lease.checkpoint({ next: 8 });
    expect(query.mock.calls[1][1]).toEqual([
      '{"next":8}',
      'tenant-a',
      'alice',
      'task',
      ctx.state.get(EXECUTION_FENCE).holder,
      9,
    ]);
    query.mockResolvedValueOnce(result());
    await expect(lease.checkpoint({ next: 9 })).rejects.toThrow('no longer owns');
  });

  it('releases every local lease on close even if one release fails', async () => {
    const { coordinator, query } = fixture();
    query.mockResolvedValueOnce(result([{ fence: 1 }])).mockResolvedValueOnce(result([{ fence: 2 }]));
    await coordinator.acquire('one', context());
    await coordinator.acquire('two', context());
    query.mockRejectedValueOnce(new Error('storage outage')).mockResolvedValueOnce(result([], 1));
    await coordinator.close();
    expect(query).toHaveBeenCalledTimes(4);
    await vi.advanceTimersByTimeAsync(1000);
    await coordinator.close();
    expect(query).toHaveBeenCalledTimes(4);
  });

  it('does not restart renewal when an in-flight heartbeat finishes after release', async () => {
    const { coordinator, query } = fixture();
    query.mockResolvedValueOnce(result([{ fence: 1 }]));
    const lease = await coordinator.acquire('task', context());
    const renewing = deferred<ReturnType<typeof result>>();
    query.mockReturnValueOnce(renewing.promise);
    await vi.advanceTimersByTimeAsync(50);
    await lease.release();
    renewing.resolve(result([{ fence: 1 }], 1));
    await vi.advanceTimersByTimeAsync(1000);
    expect(query).toHaveBeenCalledTimes(3);
    expect(lease.signal.aborted).toBe(false);
  });
});

describe('authorized cancellation and expired executions', () => {
  it.each([TaskState.TASK_STATE_COMPLETED, TaskState.TASK_STATE_FAILED, TaskState.TASK_STATE_REJECTED])(
    'does not overwrite terminal state %s',
    async (state) => {
      const { coordinator, load, save } = fixture();
      load.mockResolvedValue(task('task', state));
      await expect(coordinator.cancelTask('task', context())).rejects.toBeInstanceOf(TaskNotCancelableError);
      expect(save).not.toHaveBeenCalled();
    },
  );

  it('does not disclose an absent/other-owner task and leaves an already canceled task unchanged', async () => {
    const { coordinator, load, save } = fixture();
    const ctx = context();
    await expect(coordinator.cancelTask('hidden', ctx)).rejects.toBeInstanceOf(TaskNotFoundError);
    const canceled = task('task', TaskState.TASK_STATE_CANCELED);
    load.mockResolvedValue(canceled);
    expect(await coordinator.cancelTask('task', ctx)).toBe(canceled);
    expect(save).not.toHaveBeenCalled();
    expect(ctx.state.has(CANCEL_TASK)).toBe(false);
  });

  it('retries a conflicting update, preserving the authorized request scope and clearing its privilege', async () => {
    const { coordinator, load, save } = fixture();
    const ctx = context();
    load.mockResolvedValue(task());
    save
      .mockImplementationOnce(async (_task, scoped) => {
        expect(scoped).toBe(ctx);
        expect(scoped.state.get(CANCEL_TASK)).toBe(true);
        throw new Error('Concurrent task update; reload');
      })
      .mockImplementationOnce(async (_task, scoped) => {
        expect(scoped.state.get(CANCEL_TASK)).toBe(true);
      });
    expect((await coordinator.cancelTask('task', ctx)).status?.state).toBe(TaskState.TASK_STATE_CANCELED);
    expect(load).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenCalledTimes(2);
    expect(ctx.state.has(CANCEL_TASK)).toBe(false);
  });

  it.each([new Error('Permanent storage error'), 'non-Error failure'])(
    'does not retry arbitrary failure %s',
    async (error) => {
      const { coordinator, load, save } = fixture();
      const ctx = context();
      load.mockResolvedValue(task());
      save.mockRejectedValue(error);
      await expect(coordinator.cancelTask('task', ctx)).rejects.toBe(error);
      expect(save).toHaveBeenCalledOnce();
      expect(ctx.state.has(CANCEL_TASK)).toBe(false);
    },
  );

  it('bounds concurrent-update retries and clears cancellation privilege on exhaustion', async () => {
    const { coordinator, load, save } = fixture();
    const ctx = context();
    load.mockResolvedValue(task());
    save.mockRejectedValue(new Error('Concurrent task update'));
    await expect(coordinator.cancelTask('task', ctx)).rejects.toThrow('Concurrent task update');
    expect(save).toHaveBeenCalledTimes(3);
    expect(ctx.state.has(CANCEL_TASK)).toBe(false);
  });

  it('fails ordinary interrupted work, parks checkpointed work and preserves a concurrent terminal winner', async () => {
    const { coordinator, query, load, save } = fixture();
    const observed = new Date('2026-10-17T12:00:00Z');
    const ids = ['ordinary', 'checkpointed', 'gone', 'already-done', 'renewed'];
    query.mockResolvedValueOnce(
      result(
        ids.map((id) => ({
          tenant: 'tenant-a',
          owner: 'alice',
          task_id: id,
          fence: '4',
          observed_at: observed,
          checkpoint: id === 'checkpointed' ? { next: 2 } : null,
        })),
      ),
    );
    load
      .mockResolvedValueOnce(task('ordinary'))
      .mockResolvedValueOnce(task('checkpointed'))
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(task('already-done', TaskState.TASK_STATE_COMPLETED))
      .mockResolvedValueOnce(task('renewed'));
    save
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error('Fence replaced'));
    expect(await coordinator.reconcileExpiredTasks()).toBe(2);
    expect(save.mock.calls.map(([value]) => value.status?.state)).toEqual([
      TaskState.TASK_STATE_FAILED,
      TaskState.TASK_STATE_INPUT_REQUIRED,
      TaskState.TASK_STATE_FAILED,
    ]);
    for (const [value, scoped] of save.mock.calls) {
      expect(value.status?.timestamp).toBe(observed.toISOString());
      expect(scoped.tenant).toBe('tenant-a');
      expect(scoped.user).toMatchObject({ userName: 'alice', isAuthenticated: true });
      expect(scoped.state.get(RECOVER_EXPIRED)).toBe(4);
    }
  });

  it('keeps the background reconciler alive after a storage failure and stops scheduling on close', async () => {
    const { coordinator, query } = fixture();
    query.mockRejectedValueOnce(new Error('temporary outage')).mockResolvedValue(result());
    coordinator.start();
    await vi.advanceTimersByTimeAsync(100);
    expect(query).toHaveBeenCalledTimes(3);
    await coordinator.close();
    coordinator.start();
    await vi.advanceTimersByTimeAsync(1000);
    expect(query).toHaveBeenCalledTimes(3);
  });

  it('waits for an in-flight recovery operation before closing', async () => {
    const { coordinator, query } = fixture();
    const pending = deferred<ReturnType<typeof result>>();
    query.mockReturnValueOnce(pending.promise);
    coordinator.start();
    let closed = false;
    const stopping = coordinator.close().then(() => {
      closed = true;
    });
    await Promise.resolve();
    expect(closed).toBe(false);
    pending.resolve(result());
    await stopping;
    expect(closed).toBe(true);
    await vi.advanceTimersByTimeAsync(1000);
    expect(query).toHaveBeenCalledOnce();
  });
});

describe('remote journal subscriptions', () => {
  it('runtime close finishes active subscriptions and discards their in-flight database result', async () => {
    const { coordinator, query } = fixture();
    const pending = deferred<ReturnType<typeof result>>();
    query.mockReturnValueOnce(pending.promise);
    const bus = coordinator.eventBusManager.getByTaskId('task', context())!;
    const event = vi.fn();
    const finished = vi.fn();
    bus.on('event', event);
    bus.on('finished', finished);
    await coordinator.close();
    expect(finished).toHaveBeenCalledOnce();
    pending.resolve(result([{ revision: 1, task_data: task() }]));
    await vi.advanceTimersByTimeAsync(1000);
    expect(event).not.toHaveBeenCalled();
    expect(query).toHaveBeenCalledOnce();
  });

  it('reuses the local SDK bus and does not invent an anonymous remote subscription without context', async () => {
    const { coordinator, query } = fixture();
    const ctx = context();
    const local = coordinator.eventBusManager.createOrGetByTaskId('task', ctx);
    expect(coordinator.eventBusManager.getByTaskId('task', ctx)).toBe(local);
    expect(coordinator.eventBusManager.getByTaskId('unknown')).toBeUndefined();
    coordinator.eventBusManager.cleanupByTaskId('task', ctx);
    expect(query).not.toHaveBeenCalled();
  });

  it('polls only the authorized task scope, emits ordered revisions and closes on a remote terminal', async () => {
    const { coordinator, query } = fixture();
    const first = deferred<ReturnType<typeof result>>();
    query.mockReturnValueOnce(first.promise);
    const bus = coordinator.eventBusManager.getByTaskId('task', context())!;
    const events: AgentExecutionEvent[] = [];
    const finished = vi.fn();
    bus.on('event', (event) => events.push(event));
    bus.on('finished', finished);
    first.resolve(result([{ revision: '3', task_data: task() }]));
    await vi.advanceTimersByTimeAsync(0);
    expect(query.mock.calls[0][1]).toEqual(['tenant-a', 'alice', 'task']);
    query.mockResolvedValueOnce(
      result([
        { revision: '4', task_data: task() },
        { revision: '5', task_data: task('task', TaskState.TASK_STATE_CANCELED) },
      ]),
    );
    await vi.advanceTimersByTimeAsync(50);
    expect(query.mock.calls[1][1]).toEqual(['tenant-a', 'alice', 'task', 3]);
    expect(
      events.filter((event) => event.kind === 'statusUpdate').map((event) => event.data.metadata?.revision),
    ).toEqual([3, 4, 5]);
    expect(events.at(-1)).toMatchObject({ data: { status: { state: TaskState.TASK_STATE_CANCELED } } });
    expect(finished).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(500);
    expect(query).toHaveBeenCalledTimes(2);
  });

  it('handles an initially empty journal then a paused task without polling forever', async () => {
    const { coordinator, query } = fixture();
    const first = deferred<ReturnType<typeof result>>();
    query.mockReturnValueOnce(first.promise);
    const bus = coordinator.eventBusManager.getByTaskId('task', new ServerCallContext())!;
    const finished = vi.fn();
    bus.on('finished', finished);
    first.resolve(result());
    await vi.advanceTimersByTimeAsync(0);
    query.mockResolvedValueOnce(
      result([{ revision: 1, task_data: task('task', TaskState.TASK_STATE_INPUT_REQUIRED) }]),
    );
    await vi.advanceTimersByTimeAsync(50);
    expect(query.mock.calls[1][1]).toEqual(['', '', 'task', 0]);
    expect(finished).toHaveBeenCalledOnce();
  });

  it('closes a remote subscription on storage failure without publishing forged state', async () => {
    const { coordinator, query } = fixture();
    const pending = deferred<ReturnType<typeof result>>();
    query.mockReturnValueOnce(pending.promise);
    const bus = coordinator.eventBusManager.getByTaskId('task', context())!;
    const event = vi.fn();
    const finished = vi.fn();
    bus.on('event', event);
    bus.on('finished', finished);
    pending.reject(new Error('database unavailable'));
    await vi.advanceTimersByTimeAsync(0);
    expect(event).not.toHaveBeenCalled();
    expect(finished).toHaveBeenCalledOnce();
    await vi.advanceTimersByTimeAsync(1000);
    expect(query).toHaveBeenCalledOnce();
  });

  it('detaching the listener suppresses an in-flight result and releases the subscription', async () => {
    const { coordinator, query } = fixture();
    const pending = deferred<ReturnType<typeof result>>();
    query.mockReturnValueOnce(pending.promise);
    const bus = coordinator.eventBusManager.getByTaskId('task', context())!;
    const event = vi.fn();
    const finished = vi.fn();
    bus.on('event', event);
    bus.on('finished', finished);
    bus.off('finished', finished);
    bus.off('event', event);
    pending.resolve(result([{ revision: 1, task_data: task() }]));
    await vi.advanceTimersByTimeAsync(1000);
    expect(event).not.toHaveBeenCalled();
    expect(finished).not.toHaveBeenCalled();
    expect(query).toHaveBeenCalledOnce();
  });
});

it('ordinary Message calls do not allocate orphan execution leases', async () => {
  const { coordinator, query } = fixture();
  const skill: SkillDefinition = {
    name: 'echo',
    description: 'Echo',
    tags: [],
    inputSchema: {},
    outputSchema: {},
    isStreaming: false,
    needsTaskContext: false,
    needsInteraction: false,
    needsMcp: false,
    handler: async () => 'hello',
  };
  const executor = new LiteAgentExecutor({ skills: new Map([['echo', skill]]), executionCoordinator: coordinator });
  for (let index = 0; index < 3; index++) {
    const bus = new DefaultExecutionEventBus();
    const events: AgentExecutionEvent[] = [];
    bus.on('event', (event) => events.push(event));
    await executor.execute(
      {
        taskId: `message-${index}`,
        contextId: 'conversation',
        context: context(),
        userMessage: { parts: [{ content: { $case: 'text', value: '{"skill":"echo"}' } }] },
      } as unknown as RequestContext,
      bus,
    );
    expect(events.map((event) => event.kind)).toEqual(['message']);
  }
  expect(query).not.toHaveBeenCalled();
});
