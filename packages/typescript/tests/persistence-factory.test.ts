import { afterEach, describe, expect, it, vi } from 'vitest';
import { ServerCallContext } from '@a2a-js/sdk/server';
const state = vi.hoisted(() => ({
  pools: [] as Array<{
    query: ReturnType<typeof vi.fn>;
    end: ReturnType<typeof vi.fn>;
    connect: ReturnType<typeof vi.fn>;
  }>,
  destroyed: vi.fn(),
  stores: [] as Array<{
    load: ReturnType<typeof vi.fn>;
    save: ReturnType<typeof vi.fn>;
    list: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  }>,
}));
vi.mock('pg', () => ({
  default: {
    Pool: class {
      query = vi.fn().mockResolvedValue({ rows: [], rowCount: 0 });
      end = vi.fn().mockResolvedValue(undefined);
      connect = vi.fn().mockImplementation(async () => ({ query: this.query, release: vi.fn() }));
      constructor() {
        state.pools.push(this);
      }
    },
  },
}));
vi.mock('kysely', () => ({
  PostgresDialect: class {
    constructor(readonly options: { pool: { end: () => Promise<void> } }) {}
  },
  Kysely: class {
    constructor(private config: { dialect: { options: { pool: { end: () => Promise<void> } } } }) {}
    async destroy() {
      state.destroyed();
      await this.config.dialect.options.pool.end();
    }
  },
}));
vi.mock('@a2a-js/sdk/server/database', () => {
  class Store {
    load = vi.fn().mockResolvedValue([]);
    save = vi.fn();
    list = vi.fn().mockResolvedValue({ tasks: [] });
    delete = vi.fn();
    constructor() {
      state.stores.push(this);
    }
  }
  return { DatabaseTaskStore: Store, DatabasePushNotificationStore: Store };
});
import { createPostgresPersistence, migratePostgresRuntime } from '../src/persistence.js';
const options = {
  connectionString: 'postgresql://unused.invalid/test',
  encryptionKey: Buffer.alloc(32, 7).toString('base64'),
};
afterEach(() => {
  state.pools.length = 0;
  state.stores.length = 0;
  state.destroyed.mockClear();
});

describe('PostgreSQL factory and lifecycle boundary', () => {
  it.each([
    { encryptionKey: '' },
    { encryptionKeys: { blue: Buffer.alloc(32).toString('base64') } },
    { activeEncryptionKeyId: 'blue' },
    { encryptionKeys: { blue: Buffer.alloc(32).toString('base64') }, activeEncryptionKeyId: 'missing' },
    { taskTable: 'bad;drop' },
    { pushTable: 'A-table' },
  ])('rejects invalid configuration before allocating a connection pool', async (extra) => {
    await expect(createPostgresPersistence({ ...options, ...extra })).rejects.toThrow();
    expect(state.pools).toHaveLength(0);
  });
  it.each([{ maxPushConfigsPerTask: 0 }, { execution: {} }])(
    'releases allocated resources for incompatible settings',
    async (extra) => {
      await expect(createPostgresPersistence({ ...options, ...extra })).rejects.toThrow();
      expect(state.destroyed).toHaveBeenCalledOnce();
      expect(state.pools[0].end).toHaveBeenCalledOnce();
    },
  );
  it('requires the official schema, closes exactly once, and becomes unready during close', async () => {
    const persistence = await createPostgresPersistence({
      ...options,
      taskTable: 'custom_tasks',
      pushTable: 'custom_push',
      maxConnections: 1,
      connectionTimeoutMs: 100,
    });
    expect(persistence.durable).toBe(true);
    expect(persistence.delivery).toBeUndefined();
    expect(persistence.purgeTask).toBeUndefined();
    expect(await persistence.ready()).toBe(true);
    state.pools[0].query.mockRejectedValueOnce(new Error('missing schema'));
    expect(await persistence.ready()).toBe(false);
    const ctx = new ServerCallContext();
    await persistence.taskStore.load('task', ctx);
    await persistence.taskStore.list({ tenant: '', pageSize: 1, pageToken: '' }, ctx);
    expect(state.stores[1].load).toHaveBeenCalledWith('task', ctx);
    expect(await persistence.pushStore.load('task', ctx)).toEqual([]);
    await expect(persistence.rotateCallbackCredentials!('task', ctx)).rejects.toThrow('Authenticated');
    persistence.start!();
    await Promise.all([persistence.close(), persistence.close()]);
    expect(state.destroyed).toHaveBeenCalledOnce();
    expect(await persistence.ready()).toBe(false);
  });
  it('opens a named keyring without requiring a legacy key and leaves the worker disabled for restore', async () => {
    const persistence = await createPostgresPersistence({
      connectionString: options.connectionString,
      encryptionKeys: { blue: Buffer.alloc(32, 8).toString('base64') },
      activeEncryptionKeyId: 'blue',
      delivery: { autoStart: false },
    });
    expect(persistence.delivery).toBeDefined();
    expect(persistence.execution).toBeUndefined();
    expect(persistence.purgeTask).toBeTypeOf('function');
    persistence.start!();
    expect(state.pools[0].query).not.toHaveBeenCalled();
    await persistence.pushSender!.send({ payload: undefined }, new ServerCallContext());
    expect(await persistence.ready()).toBe(true);
    state.pools[0].query
      .mockResolvedValueOnce({ rows: [] })
      .mockResolvedValueOnce({ rows: [] })
      .mockRejectedValueOnce(new Error('missing extension'));
    expect(await persistence.ready()).toBe(false);
    await persistence.close();
    expect(state.destroyed).toHaveBeenCalledOnce();
  });
  it('starts coordination independently of outbound workers and closes its background activity', async () => {
    const persistence = await createPostgresPersistence({ ...options, delivery: { autoStart: false }, execution: {} });
    persistence.start!();
    await Promise.resolve();
    expect(state.pools[0].query).toHaveBeenCalledOnce();
    await persistence.close();
    expect(state.pools[0].end).toHaveBeenCalledOnce();
  });
  it('closes the temporary migration pool even when schema setup fails', async () => {
    await migratePostgresRuntime({ connectionString: options.connectionString });
    expect(state.pools[0].end).toHaveBeenCalledOnce();
    const failing = migratePostgresRuntime({
      connectionString: options.connectionString,
      delivery: { tablePrefix: 'unsafe;sql' },
    });
    await expect(failing).rejects.toThrow('prefix');
    expect(state.pools[1].end).toHaveBeenCalledOnce();
  });
});
