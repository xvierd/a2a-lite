import { randomUUID } from 'node:crypto';
import type { Kysely, Transaction } from 'kysely';
import type pg from 'pg';
import {
  ServerCallContext,
  V1PushNotificationSerializer,
  type PushNotificationStore,
  type TaskStore,
} from '@a2a-js/sdk/server';
import { TaskState, type Task } from '@a2a-js/sdk';
import {
  EXECUTION_FENCE,
  CANCEL_TASK,
  PERSISTED_CANCEL,
  CANCEL_OBSERVER,
  RECOVER_EXPIRED,
} from './postgres-execution.js';
import { postWebhook } from './push-delivery.js';

export interface DurableDeliveryOptions {
  /** Disable automatic workers during restore/inspection; dispatchOnce remains explicit. */
  autoStart?: boolean;
  tablePrefix?: string;
  pollIntervalMs?: number;
  leaseMs?: number;
  maxAttempts?: number;
  retryBaseMs?: number;
  maxPending?: number;
  maxAgeMs?: number;
}
export interface DeliveryStatus {
  pending: number;
  delivered: number;
  dead: number;
  canceled: number;
}
export interface DurableDelivery {
  dispatchOnce(): Promise<boolean>;
  status(): Promise<DeliveryStatus>;
  replay(id: string, context: ServerCallContext): Promise<boolean>;
  prune(before: Date): Promise<number>;
}
export function runtimeTableNames(prefix = 'a2a_lite'): { outbox: string; versions: string } {
  if (!/^[a-z_][a-z0-9_]{0,24}$/.test(prefix)) throw new Error('Invalid runtime table prefix');
  return { outbox: prefix + '_outbox', versions: prefix + '_versions' };
}

/** Explicit additive migration for the Lite transaction/outbox extension. */
export async function migrateRuntimeTables(pool: pg.Pool, prefix?: string): Promise<void> {
  const { outbox, versions } = runtimeTableNames(prefix);
  const connection = await pool.connect();
  try {
    await connection.query('BEGIN');
    await connection.query('SELECT pg_advisory_xact_lock(hashtext($1))', [outbox + ':migration']);
    await connection.query(
      `CREATE TABLE IF NOT EXISTS ${versions} (tenant text NOT NULL, owner text NOT NULL, task_id text NOT NULL, revision bigint NOT NULL, PRIMARY KEY (tenant, owner, task_id))`,
    );
    await connection.query(`ALTER TABLE ${versions} ADD COLUMN IF NOT EXISTS purged boolean NOT NULL DEFAULT false`);
    await connection.query(
      `CREATE TABLE IF NOT EXISTS ${outbox} (id text PRIMARY KEY, tenant text NOT NULL, owner text NOT NULL, task_id text NOT NULL, config_id text NOT NULL, body text NOT NULL, content_type text NOT NULL, status text NOT NULL DEFAULT 'pending', attempts integer NOT NULL DEFAULT 0, available_at timestamptz NOT NULL DEFAULT now(), lease_until timestamptz, lease_token text, created_at timestamptz NOT NULL DEFAULT now())`,
    );
    await connection.query(
      `CREATE INDEX IF NOT EXISTS ${outbox}_due_idx ON ${outbox} (status, available_at, lease_until)`,
    );
    await connection.query(
      `CREATE TABLE IF NOT EXISTS ${prefix ?? 'a2a_lite'}_leases (tenant text NOT NULL,owner text NOT NULL,task_id text NOT NULL,holder text NOT NULL,fence bigint NOT NULL,lease_until timestamptz NOT NULL,cancel_requested boolean NOT NULL DEFAULT false,checkpoint jsonb,PRIMARY KEY(tenant,owner,task_id))`,
    );
    await connection.query(
      `CREATE TABLE IF NOT EXISTS ${prefix ?? 'a2a_lite'}_journal (tenant text NOT NULL,owner text NOT NULL,task_id text NOT NULL,revision bigint NOT NULL,task_data jsonb NOT NULL,PRIMARY KEY(tenant,owner,task_id,revision))`,
    );
    await connection.query('COMMIT');
  } catch (error) {
    await connection.query('ROLLBACK');
    throw error;
  } finally {
    connection.release();
  }
}

/** Local workers may share these PostgreSQL leases; callbacks remain at-least-once. */
export class PostgresDelivery implements DurableDelivery {
  private readonly tables;
  private readonly options: Required<DurableDeliveryOptions>;
  private readonly serializer = new V1PushNotificationSerializer();
  private timer?: ReturnType<typeof setTimeout>;
  private running?: Promise<void>;
  private stopped = false;
  readonly taskStore: TaskStore;
  constructor(
    private readonly db: Kysely<Record<string, never>>,
    private readonly pool: pg.Pool,
    private readonly pushStore: PushNotificationStore,
    private readonly transactionalPushStore: (tx: Transaction<Record<string, never>>) => PushNotificationStore,
    taskTable: string,
    options: DurableDeliveryOptions,
    private readonly DatabaseTaskStore: typeof import('@a2a-js/sdk/server/database').DatabaseTaskStore,
  ) {
    this.tables = runtimeTableNames(options.tablePrefix);
    this.options = {
      autoStart: true,
      tablePrefix: 'a2a_lite',
      pollIntervalMs: 1000,
      leaseMs: 15000,
      maxAttempts: 8,
      retryBaseMs: 1000,
      maxPending: 10000,
      maxAgeMs: 24 * 60 * 60 * 1000,
      ...options,
    };
    if (typeof this.options.autoStart !== 'boolean') throw new Error('Invalid delivery worker setting');
    for (const [key, value] of Object.entries(this.options))
      if (key !== 'tablePrefix' && key !== 'autoStart' && (!Number.isSafeInteger(value) || Number(value) < 1))
        throw new Error('Invalid durable delivery limit');
    if (this.options.leaseMs < 10000) throw new Error('Delivery lease must exceed callback deadline');
    const base = new this.DatabaseTaskStore(db, { tableName: taskTable });
    this.taskStore = {
      load: async (id, context) => {
        const { sql } = await import('kysely');
        return db
          .transaction()
          .setIsolationLevel('repeatable read')
          .execute(async (tx) => {
            const task = await new this.DatabaseTaskStore(tx, { tableName: taskTable }).load(id, context);
            const rows = await sql<{
              revision: string;
            }>`SELECT revision FROM ${sql.table(this.tables.versions)} WHERE tenant=${context.tenant ?? ''} AND owner=${context.user?.userName ?? ''} AND task_id=${id}`.execute(
              tx,
            );
            context.state.set(this.revisionKey(id), Number(rows.rows[0]?.revision ?? 0));
            this.observeCancellation(task, context);
            return task;
          });
      },
      list: (params, context) => base.list(params, context),
      save: async (task, context) => {
        const { sql } = await import('kysely');
        const tenant = context.tenant ?? '';
        const owner = context.user?.userName ?? '';
        const expected = Number(context.state.get(this.revisionKey(task.id)) ?? 0);
        const savedRevision = await db.transaction().execute(async (tx) => {
          // Serializes a task across replicas before validating its observed revision.
          await sql`SELECT pg_advisory_xact_lock(hashtext(${JSON.stringify([tenant, owner, task.id])}))`.execute(tx);
          const current = await sql<{
            revision: string;
            purged: boolean;
          }>`SELECT revision,purged FROM ${sql.table(this.tables.versions)} WHERE tenant=${tenant} AND owner=${owner} AND task_id=${task.id}`.execute(
            tx,
          );
          const revision = Number(current.rows[0]?.revision ?? 0);
          if (current.rows[0]?.purged) throw new Error('Task has been purged');
          const store = new this.DatabaseTaskStore(tx, { tableName: taskTable });
          const previous = await store.load(task.id, context);

          // A remote cancel is authoritative. Reconcile queued executor events without
          // writing stale state, even if cancellation invalidated the observed revision.
          if (this.observeCancellation(previous, context)) return revision;
          if (revision !== expected) throw new Error('Concurrent task update; reload the task before retrying');
          if (
            previous &&
            [
              TaskState.TASK_STATE_COMPLETED,
              TaskState.TASK_STATE_FAILED,
              TaskState.TASK_STATE_CANCELED,
              TaskState.TASK_STATE_REJECTED,
            ].includes(previous.status!.state) &&
            previous.status!.state !== task.status!.state
          )
            throw new Error('Terminal task state cannot be overwritten');
          const lease = context.state.get(EXECUTION_FENCE) as { holder: string; fence: number } | undefined;
          const prefix = this.options.tablePrefix;
          const expiredFence = context.state.get(RECOVER_EXPIRED);
          if (expiredFence !== undefined) {
            const expired =
              await sql`UPDATE ${sql.table(prefix + '_leases')} SET fence=fence+1 WHERE tenant=${tenant} AND owner=${owner} AND task_id=${task.id} AND fence=${expiredFence} AND lease_until<now() AND NOT cancel_requested RETURNING fence`.execute(
                tx,
              );
            if (!expired.rows.length) throw new Error('Execution lease is no longer expired');
          }
          if (lease) {
            const owned =
              await sql`SELECT fence FROM ${sql.table(prefix + '_leases')} WHERE tenant=${tenant} AND owner=${owner} AND task_id=${task.id} AND holder=${lease.holder} AND fence=${lease.fence} AND lease_until>now() AND NOT cancel_requested FOR UPDATE`.execute(
                tx,
              );
            if (!owned.rows.length) throw new Error('Stale execution fence');
          }
          if (context.state.get(CANCEL_TASK))
            await sql`UPDATE ${sql.table(prefix + '_leases')} SET cancel_requested=true,fence=fence+1,lease_until=now() WHERE tenant=${tenant} AND owner=${owner} AND task_id=${task.id}`.execute(
              tx,
            );
          await store.save(task, context);
          await sql`INSERT INTO ${sql.table(this.tables.versions)} (tenant,owner,task_id,revision) VALUES (${tenant},${owner},${task.id},${revision + 1}) ON CONFLICT (tenant,owner,task_id) DO UPDATE SET revision=EXCLUDED.revision`.execute(
            tx,
          );
          await sql`INSERT INTO ${sql.table(this.options.tablePrefix + '_journal')} (tenant,owner,task_id,revision,task_data) VALUES (${tenant},${owner},${task.id},${revision + 1},${JSON.stringify(task)}::jsonb)`.execute(
            tx,
          );
          await sql`DELETE FROM ${sql.table(this.options.tablePrefix + '_journal')} WHERE tenant=${tenant} AND owner=${owner} AND task_id=${task.id} AND revision<=${revision + 1 - 16}`.execute(
            tx,
          );
          if (
            lease &&
            task.status &&
            [
              TaskState.TASK_STATE_COMPLETED,
              TaskState.TASK_STATE_FAILED,
              TaskState.TASK_STATE_CANCELED,
              TaskState.TASK_STATE_INPUT_REQUIRED,
              TaskState.TASK_STATE_REJECTED,
            ].includes(task.status.state)
          )
            await sql`UPDATE ${sql.table(this.options.tablePrefix + '_leases')} SET lease_until=now() WHERE tenant=${tenant} AND owner=${owner} AND task_id=${task.id} AND holder=${lease.holder} AND fence=${lease.fence}`.execute(
              tx,
            );
          if (context.user?.isAuthenticated) await this.enqueue(tx, task, context);
          return revision + 1;
        });
        context.state.set(this.revisionKey(task.id), savedRevision);
      },
    };
  }
  private observeCancellation(task: Task | undefined, context: ServerCallContext): boolean {
    if (!context.state.has(EXECUTION_FENCE) || task?.status?.state !== TaskState.TASK_STATE_CANCELED) return false;
    context.state.set(PERSISTED_CANCEL, task);
    const observer = context.state.get(CANCEL_OBSERVER) as (() => void) | undefined;
    context.state.delete(CANCEL_OBSERVER);
    observer?.();
    return true;
  }
  private revisionKey(id: string): string {
    return this.tables.versions + ':' + id;
  }
  private async enqueue(tx: Transaction<Record<string, never>>, task: Task, context: ServerCallContext): Promise<void> {
    const { sql } = await import('kysely');
    // Serialize enqueue with deletion/rotation so deleting a subscription also
    // invalidates every event committed before the deletion boundary.
    await sql`SELECT pg_advisory_xact_lock(hashtext(${JSON.stringify(['push', context.tenant ?? '', context.user?.userName ?? '', task.id])}))`.execute(
      tx,
    );
    const configs = await this.transactionalPushStore(tx).load(task.id, context);
    if (!configs.length) return;
    const { body, contentType } = this.serializer.serialize({ payload: { $case: 'task', value: task } }, task);
    // Bounds the queue atomically across workers. Registration itself remains separate.
    await sql`SELECT pg_advisory_xact_lock(hashtext(${this.tables.outbox + ':capacity'}))`.execute(tx);
    const count = await sql<{
      count: string;
    }>`SELECT count(*) FROM ${sql.table(this.tables.outbox)} WHERE status='pending'`.execute(tx);
    if (Number(count.rows[0].count) + configs.length > this.options.maxPending)
      throw new Error('Durable delivery capacity unavailable');
    for (const config of configs)
      await sql`INSERT INTO ${sql.table(this.tables.outbox)} (id,tenant,owner,task_id,config_id,body,content_type) VALUES (${randomUUID()},${context.tenant ?? ''},${context.user!.userName},${task.id},${config.id},${body},${contentType})`.execute(
        tx,
      );
  }
  async ready(): Promise<boolean> {
    try {
      await this.pool.query(`SELECT id FROM ${this.tables.outbox} LIMIT 0`);
      await this.pool.query(`SELECT revision FROM ${this.tables.versions} LIMIT 0`);
      return true;
    } catch {
      return false;
    }
  }
  start(): void {
    const tick = async () => {
      if (this.stopped) return;
      this.running = this.dispatchOnce().then(
        () => {},
        () => {},
      );
      await this.running;
      if (!this.stopped) {
        this.timer = setTimeout(() => {
          void tick();
        }, this.options.pollIntervalMs);
        this.timer.unref();
      }
    };
    void tick();
  }
  async stop(): Promise<void> {
    this.stopped = true;
    clearTimeout(this.timer);
    await this.running;
  }
  async dispatchOnce(): Promise<boolean> {
    const token = randomUUID();
    // Exhausted claims include workers that crashed before acknowledging their final attempt.
    const expired = await this.pool.query(
      `UPDATE ${this.tables.outbox} SET status='dead',lease_until=NULL,lease_token=NULL WHERE status='pending' AND (lease_until IS NULL OR lease_until<now()) AND (attempts >= $1 OR created_at <= now()-($2 * interval '1 millisecond'))`,
      [this.options.maxAttempts, this.options.maxAgeMs],
    );
    const result = await this.pool.query(
      `UPDATE ${this.tables.outbox} SET lease_until=now()+($1 * interval '1 millisecond'), lease_token=$2, attempts=attempts+1 WHERE id=(SELECT id FROM ${this.tables.outbox} WHERE status='pending' AND attempts<$3 AND created_at>now()-($4 * interval '1 millisecond') AND available_at<=now() AND (lease_until IS NULL OR lease_until<now()) ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *`,
      [this.options.leaseMs, token, this.options.maxAttempts, this.options.maxAgeMs],
    );
    const row = result.rows[0];
    if (!row) return (expired.rowCount ?? 0) > 0;
    let delivered = false;
    try {
      if (row.attempts > this.options.maxAttempts) throw new Error('Attempts exhausted');
      const context = new ServerCallContext({
        user: { userName: row.owner, isAuthenticated: true },
        tenant: row.tenant,
      });
      const config = (await this.pushStore.load(row.task_id, context)).find((config) => config.id === row.config_id);
      if (!config)
        delivered = true; // Revoked subscription: discard without making a callback.
      else {
        const headers: Record<string, string> = { 'Content-Type': row.content_type, 'X-A2A-Delivery-Id': row.id };
        if (config.authentication?.credentials)
          headers.Authorization = `${config.authentication.scheme} ${config.authentication.credentials}`;
        if (config.token) headers['X-A2A-Notification-Token'] = config.token;
        await postWebhook(config.url, { body: row.body, headers, timeoutMs: 5000 });
        delivered = true;
      }
    } catch {
      /* Delivery errors never include callback credentials or URL. */
    }
    const status = delivered ? 'delivered' : row.attempts >= this.options.maxAttempts ? 'dead' : 'pending';
    const backoff =
      Math.min(3600000, this.options.retryBaseMs * 2 ** Math.min(row.attempts - 1, 20)) * (0.75 + Math.random() * 0.5);
    await this.pool.query(
      `UPDATE ${this.tables.outbox} SET status=$1, available_at=now()+($2 * interval '1 millisecond'), lease_until=NULL, lease_token=NULL WHERE id=$3 AND lease_token=$4`,
      [status, Math.ceil(backoff), row.id, token],
    );
    return true;
  }
  async status(): Promise<DeliveryStatus> {
    const result = await this.pool.query(`SELECT status,count(*) AS count FROM ${this.tables.outbox} GROUP BY status`);
    const status = { pending: 0, delivered: 0, dead: 0, canceled: 0 };
    for (const row of result.rows)
      if (row.status in status) status[row.status as keyof DeliveryStatus] = Number(row.count);
    return status;
  }
  async replay(id: string, context: ServerCallContext): Promise<boolean> {
    if (!context.user?.isAuthenticated) return false;
    const result = await this.pool.query(
      `UPDATE ${this.tables.outbox} SET status='pending', attempts=0, created_at=now(), available_at=now(), lease_until=NULL, lease_token=NULL WHERE id=$1 AND tenant=$2 AND owner=$3 AND status='dead'`,
      [id, context.tenant ?? '', context.user.userName],
    );
    return (result.rowCount ?? 0) === 1;
  }
  /** Remove terminal payloads only; a revision tombstone prevents stale resurrection. */
  async purgeTask(
    id: string,
    before: Date,
    context: ServerCallContext,
    taskTable: string,
    pushTable: string,
  ): Promise<boolean> {
    if (!context.user?.isAuthenticated) throw new Error('Authenticated owner required');
    if (!Number.isFinite(before.getTime())) throw new Error('Invalid retention cutoff');
    const { sql } = await import('kysely');
    const tenant = context.tenant ?? '';
    const owner = context.user.userName;
    return this.db.transaction().execute(async (tx) => {
      await sql`SELECT pg_advisory_xact_lock(hashtext(${JSON.stringify([tenant, owner, id])}))`.execute(tx);
      await sql`SELECT pg_advisory_xact_lock(hashtext(${JSON.stringify(['push', tenant, owner, id])}))`.execute(tx);
      const eligible =
        await sql`SELECT id FROM ${sql.table(taskTable)} WHERE tenant=${tenant} AND owner=${owner} AND id=${id} AND status_state IN ('TASK_STATE_COMPLETED','TASK_STATE_FAILED','TASK_STATE_CANCELED','TASK_STATE_REJECTED') AND status_last_updated<${before.getTime()} FOR UPDATE`.execute(
          tx,
        );
      if (!eligible.rows.length) return false;
      const pending =
        await sql`SELECT id FROM ${sql.table(this.tables.outbox)} WHERE tenant=${tenant} AND owner=${owner} AND task_id=${id} AND status='pending' LIMIT 1`.execute(
          tx,
        );
      if (pending.rows.length) return false;
      await sql`INSERT INTO ${sql.table(this.tables.versions)} (tenant,owner,task_id,revision,purged) VALUES (${tenant},${owner},${id},1,true) ON CONFLICT (tenant,owner,task_id) DO UPDATE SET revision=${sql.table(this.tables.versions)}.revision+1,purged=true`.execute(
        tx,
      );
      for (const table of [
        pushTable,
        this.tables.outbox,
        this.options.tablePrefix + '_journal',
        this.options.tablePrefix + '_leases',
      ])
        await sql`DELETE FROM ${sql.table(table)} WHERE tenant=${tenant} AND owner=${owner} AND task_id=${id}`.execute(
          tx,
        );
      await sql`DELETE FROM ${sql.table(taskTable)} WHERE tenant=${tenant} AND owner=${owner} AND id=${id}`.execute(tx);
      return true;
    });
  }
  async prune(before: Date): Promise<number> {
    const result = await this.pool.query(
      `DELETE FROM ${this.tables.outbox} WHERE status IN ('delivered','dead','canceled') AND created_at<$1`,
      [before],
    );
    return result.rowCount ?? 0;
  }
}
