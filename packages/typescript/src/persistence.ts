import {
  PostgresDelivery,
  migrateRuntimeTables,
  type DurableDeliveryOptions,
  type DurableDelivery,
} from './postgres-delivery.js';
import {
  PostgresExecution,
  type DistributedExecution,
  type DistributedExecutionOptions,
} from './postgres-execution.js';
import { EncryptedPushStore } from './encrypted-push-store.js';
import type { TaskStore, PushNotificationStore, ServerCallContext } from '@a2a-js/sdk/server';

/** Durable protocol state. It does not recover interrupted skill execution. */
export interface ProtocolPersistence {
  readonly durable: true;
  readonly taskStore: TaskStore;
  readonly pushStore: PushNotificationStore;
  readonly delivery?: DurableDelivery;
  readonly execution?: DistributedExecution;
  readonly pushSender?: import('@a2a-js/sdk/server').PushNotificationSender;
  rotateCallbackCredentials?(taskId: string, context: ServerCallContext): Promise<number>;
  /** Terminal retention requires the transactional runtime extension. */
  purgeTask?(taskId: string, before: Date, context: ServerCallContext): Promise<boolean>;
  start?(): void;
  ready(): Promise<boolean>;
  close(): Promise<void>;
}

export interface PostgresPersistenceOptions {
  connectionString: string;
  /** Base64-encoded 32-byte key, managed separately from PostgreSQL backups. */
  encryptionKey?: string;
  /** Named base64 keys for online rotation. Retain old keys through backup retention. */
  encryptionKeys?: Readonly<Record<string, string>>;
  activeEncryptionKeyId?: string;
  taskTable?: string;
  pushTable?: string;
  delivery?: DurableDeliveryOptions;
  execution?: DistributedExecutionOptions;
  maxPushConfigsPerTask?: number;
  maxConnections?: number;
  connectionTimeoutMs?: number;
}

/** Connect to official SDK SQL stores. Run `a2a-db upgrade` explicitly before startup. */
export async function createPostgresPersistence(options: PostgresPersistenceOptions): Promise<ProtocolPersistence> {
  const [{ Kysely, PostgresDialect }, { default: pg }, { DatabaseTaskStore, DatabasePushNotificationStore }] =
    await Promise.all([import('kysely'), import('pg'), import('@a2a-js/sdk/server/database')]);
  if (options.activeEncryptionKeyId && !options.encryptionKeys)
    throw new Error('Named callback encryption keys are required');
  const encryptionKey = options.encryptionKeys
    ? {
        keys: Object.fromEntries(
          Object.entries(options.encryptionKeys).map(([id, value]) => [id, Buffer.from(value, 'base64')]),
        ),
        activeKeyId: options.activeEncryptionKeyId ?? '',
        legacyKey: options.encryptionKey ? Buffer.from(options.encryptionKey, 'base64') : undefined,
      }
    : Buffer.from(options.encryptionKey ?? '', 'base64');
  // Validate before allocating database resources.
  new EncryptedPushStore({ save: async () => {}, load: async () => [], delete: async () => {} }, encryptionKey);
  const taskTable = options.taskTable ?? 'tasks';
  const pushTable = options.pushTable ?? 'push_notification_configs';
  for (const name of [taskTable, pushTable])
    if (!/^[a-z_][a-z0-9_]{0,36}$/.test(name)) throw new Error('Invalid protocol table name');
  const pool = new pg.Pool({
    connectionString: options.connectionString,
    max: options.maxConnections ?? 10,
    connectionTimeoutMillis: options.connectionTimeoutMs ?? 5000,
    statement_timeout: 5000,
  });
  const db = new Kysely<Record<string, never>>({ dialect: new PostgresDialect({ pool }) });
  const encrypted = new EncryptedPushStore(
    new DatabasePushNotificationStore(db, { tableName: pushTable }),
    encryptionKey,
  );
  const maxConfigs = options.maxPushConfigsPerTask ?? 8;
  if (!Number.isSafeInteger(maxConfigs) || maxConfigs < 1) {
    await db.destroy();
    throw new Error('Invalid callback configuration limit');
  }
  const pushStore: PushNotificationStore = {
    load: (id, context) => encrypted.load(id, context),
    delete: async (id, context, configId) => {
      const { sql } = await import('kysely');
      await db.transaction().execute(async (tx) => {
        await sql`SELECT pg_advisory_xact_lock(hashtext(${JSON.stringify(['push', context.tenant ?? '', context.user?.userName ?? '', id])}))`.execute(
          tx,
        );
        await new DatabasePushNotificationStore(tx, { tableName: pushTable }).delete(id, context, configId);
        if (options.delivery) {
          const filter = configId === undefined ? sql`true` : sql`config_id=${configId}`;
          await sql`UPDATE ${sql.table((options.delivery.tablePrefix ?? 'a2a_lite') + '_outbox')} SET status='canceled',lease_until=NULL,lease_token=NULL WHERE tenant=${context.tenant ?? ''} AND owner=${context.user?.userName ?? ''} AND task_id=${id} AND ${filter} AND status IN ('pending','dead')`.execute(
            tx,
          );
        }
      });
    },
    save: async (id, context, config) => {
      const { sql } = await import('kysely');
      await db.transaction().execute(async (tx) => {
        await sql`SELECT pg_advisory_xact_lock(hashtext(${JSON.stringify(['push', context.tenant ?? '', context.user?.userName ?? '', id])}))`.execute(
          tx,
        );
        const store = new EncryptedPushStore(
          new DatabasePushNotificationStore(tx, { tableName: pushTable }),
          encryptionKey,
        );
        if (options.delivery) {
          const tombstone = await sql<{
            purged: boolean;
          }>`SELECT purged FROM ${sql.table((options.delivery.tablePrefix ?? 'a2a_lite') + '_versions')} WHERE tenant=${context.tenant ?? ''} AND owner=${context.user?.userName ?? ''} AND task_id=${id}`.execute(
            tx,
          );
          if (tombstone.rows[0]?.purged) throw new Error('Task has been purged');
        }
        const configs = await store.load(id, context);
        if (!configs.some((existing) => existing.id === config.id) && configs.length >= maxConfigs)
          throw new Error('Push notification configuration limit reached');
        await store.save(id, context, config);
      });
    },
  };
  if (options.execution && !options.delivery) {
    await db.destroy();
    throw new Error('Distributed execution requires the transactional delivery extension');
  }
  const delivery = options.delivery
    ? new PostgresDelivery(
        db,
        pool,
        pushStore,
        (tx) => new EncryptedPushStore(new DatabasePushNotificationStore(tx, { tableName: pushTable }), encryptionKey),
        taskTable,
        options.delivery,
        DatabaseTaskStore,
      )
    : undefined;
  const execution =
    options.execution && delivery
      ? new PostgresExecution(
          pool,
          delivery.taskStore,
          options.delivery?.tablePrefix ?? 'a2a_lite',
          options.execution,
          taskTable,
        )
      : undefined;
  let closing: Promise<void> | undefined;
  return {
    durable: true,
    taskStore: delivery?.taskStore ?? new DatabaseTaskStore(db, { tableName: taskTable }),
    pushStore,
    delivery,
    execution,
    async rotateCallbackCredentials(id, context) {
      if (!context.user?.isAuthenticated) throw new Error('Authenticated owner required');
      const { sql } = await import('kysely');
      return db.transaction().execute(async (tx) => {
        await sql`SELECT pg_advisory_xact_lock(hashtext(${JSON.stringify(['push', context.tenant ?? '', context.user!.userName, id])}))`.execute(
          tx,
        );
        if (!(await new DatabaseTaskStore(tx, { tableName: taskTable }).load(id, context)))
          throw new Error('Task not found');
        const store = new EncryptedPushStore(
          new DatabasePushNotificationStore(tx, { tableName: pushTable }),
          encryptionKey,
        );
        const configs = await store.load(id, context);
        for (const config of configs) await store.save(id, context, config);
        return configs.length;
      });
    },
    purgeTask: delivery
      ? (id, before, context) => delivery.purgeTask(id, before, context, taskTable, pushTable)
      : undefined,
    pushSender: delivery ? { send: async () => {} } : undefined,
    start: () => {
      if (options.delivery?.autoStart !== false) delivery?.start();
      execution?.start();
    },
    async ready() {
      if (closing) return false;
      try {
        // Check usable schemas and access, not merely an open TCP connection.
        await pool.query(`SELECT tenant, owner, id, status FROM ${taskTable} LIMIT 0`);
        await pool.query(`SELECT tenant, owner, task_id, config_id, config_data FROM ${pushTable} LIMIT 0`);
        return delivery ? delivery.ready() : true;
      } catch {
        return false;
      }
    },
    close() {
      closing ??= (async () => {
        await execution?.close();
        await delivery?.stop();
        await db.destroy();
      })();
      return closing;
    },
  };
}

/** Run only as an operator migration step, after the official SDK migration. */
export async function migratePostgresRuntime(
  options: Pick<PostgresPersistenceOptions, 'connectionString' | 'delivery'>,
): Promise<void> {
  const { default: pg } = await import('pg');
  const pool = new pg.Pool({ connectionString: options.connectionString, connectionTimeoutMillis: 5000 });
  try {
    await migrateRuntimeTables(pool, options.delivery?.tablePrefix);
  } finally {
    await pool.end();
  }
}
