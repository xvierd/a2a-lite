import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Kysely } from 'kysely';
import type pg from 'pg';
import { ServerCallContext, type PushNotificationStore } from '@a2a-js/sdk/server';
import type { TaskPushNotificationConfig } from '@a2a-js/sdk';
import {
  PostgresDelivery,
  migrateRuntimeTables,
  runtimeTableNames,
  type DurableDeliveryOptions,
} from '../src/postgres-delivery.js';
import { postWebhook } from '../src/push-delivery.js';
vi.mock('../src/push-delivery.js', () => ({ postWebhook: vi.fn() }));
afterEach(() => {
  vi.useRealTimers();
  vi.mocked(postWebhook).mockReset();
});
const row = (attempts = 1) => ({
  id: 'stable-delivery',
  tenant: 'team',
  owner: 'alice',
  task_id: 'task',
  config_id: 'hook',
  body: '{"task":"payload"}',
  content_type: 'application/a2a+json',
  attempts,
});
const config = (): TaskPushNotificationConfig => ({
  taskId: 'task',
  id: 'hook',
  url: 'https://public.example/hook',
  token: 'token',
  authentication: { scheme: 'Bearer', credentials: 'credential' },
});
function fixture(options: DurableDeliveryOptions = {}) {
  const query = vi.fn().mockResolvedValue({ rows: [], rowCount: 0 });
  const push = { load: vi.fn().mockResolvedValue([config()]), save: vi.fn(), delete: vi.fn() };
  class FakeTaskStore {
    load = vi.fn();
    save = vi.fn();
    list = vi.fn();
  }
  const delivery = new PostgresDelivery(
    {} as Kysely<Record<string, never>>,
    { query } as unknown as pg.Pool,
    push as PushNotificationStore,
    () => push as PushNotificationStore,
    'tasks',
    options,
    FakeTaskStore as unknown as typeof import('@a2a-js/sdk/server/database').DatabaseTaskStore,
  );
  const claim = (attempts = 1) =>
    query
      .mockResolvedValueOnce({ rows: [], rowCount: 0 })
      .mockResolvedValueOnce({ rows: [row(attempts)], rowCount: 1 });
  return { delivery, query, push, claim };
}

describe('durable callback worker contracts', () => {
  it.each([
    { leaseMs: 9999 },
    { maxAttempts: 0 },
    { maxAgeMs: NaN },
    { retryBaseMs: 0.5 },
    { maxPending: -1 },
    { pollIntervalMs: Infinity },
    { autoStart: 'yes' as unknown as boolean },
    { tablePrefix: 'unsafe;sql' },
  ])('rejects invalid worker settings before dispatch', (options) => {
    expect(() => fixture(options)).toThrow();
  });
  it('uses the committed body, both credentials and stable delivery identity, then acknowledges only its claim', async () => {
    const { delivery, query, push, claim } = fixture();
    claim();
    vi.mocked(postWebhook).mockResolvedValue(undefined);
    expect(await delivery.dispatchOnce()).toBe(true);
    const context = push.load.mock.calls[0][1] as ServerCallContext;
    expect(context.tenant).toBe('team');
    expect(context.user?.userName).toBe('alice');
    expect(context.user?.isAuthenticated).toBe(true);
    expect(postWebhook).toHaveBeenCalledWith('https://public.example/hook', {
      body: row().body,
      timeoutMs: 5000,
      headers: {
        'Content-Type': row().content_type,
        'X-A2A-Delivery-Id': row().id,
        Authorization: 'Bearer credential',
        'X-A2A-Notification-Token': 'token',
      },
    });
    const parameters = query.mock.calls.at(-1)![1];
    expect(parameters[0]).toBe('delivered');
    expect(parameters[2]).toBe(row().id);
    expect(parameters[3]).toBe(query.mock.calls[1][1][1]);
  });
  it.each([1, 3])(
    'retries failures within the configured budget and dead-letters the last attempt (%s)',
    async (attempts) => {
      const { delivery, query, claim } = fixture({ maxAttempts: 3, retryBaseMs: 100 });
      claim(attempts);
      vi.mocked(postWebhook).mockRejectedValue(new Error('private callback credentials must not escape'));
      expect(await delivery.dispatchOnce()).toBe(true);
      const parameters = query.mock.calls.at(-1)![1];
      expect(parameters[0]).toBe(attempts === 3 ? 'dead' : 'pending');
      expect(parameters[1]).toBeGreaterThanOrEqual(75 * 2 ** (attempts - 1));
      expect(parameters[1]).toBeLessThanOrEqual(125 * 2 ** (attempts - 1));
    },
  );
  it('does not deliver revoked or exhausted claims', async () => {
    const revoked = fixture();
    revoked.claim();
    revoked.push.load.mockResolvedValue([]);
    expect(await revoked.delivery.dispatchOnce()).toBe(true);
    expect(revoked.query.mock.calls.at(-1)![1][0]).toBe('delivered');
    const exhausted = fixture({ maxAttempts: 1 });
    exhausted.claim(2);
    expect(await exhausted.delivery.dispatchOnce()).toBe(true);
    expect(exhausted.query.mock.calls.at(-1)![1][0]).toBe('dead');
    expect(exhausted.push.load).not.toHaveBeenCalled();
    expect(postWebhook).not.toHaveBeenCalled();
  });
  it('omits absent authentication while keeping token-only notifications intact', async () => {
    const value = fixture();
    value.claim();
    value.push.load.mockResolvedValue([{ ...config(), authentication: undefined }]);
    await value.delivery.dispatchOnce();
    expect(vi.mocked(postWebhook).mock.calls[0][1].headers).not.toHaveProperty('Authorization');
    expect(vi.mocked(postWebhook).mock.calls[0][1].headers['X-A2A-Notification-Token']).toBe('token');
    value.claim();
    value.push.load.mockResolvedValue([{ ...config(), authentication: undefined, token: '' }]);
    await value.delivery.dispatchOnce();
    expect(vi.mocked(postWebhook).mock.calls[1][1].headers).not.toHaveProperty('X-A2A-Notification-Token');
  });
  it('reports expiration work without an external attempt and returns false when idle', async () => {
    const { delivery, query } = fixture();
    query.mockResolvedValueOnce({ rows: [], rowCount: 2 });
    expect(await delivery.dispatchOnce()).toBe(true);
    expect(postWebhook).not.toHaveBeenCalled();
    expect(await delivery.dispatchOnce()).toBe(false);
  });
  it('keeps readiness false on storage failure and reports known queue states', async () => {
    const { delivery, query } = fixture();
    expect(await delivery.ready()).toBe(true);
    query.mockRejectedValueOnce(new Error('offline'));
    expect(await delivery.ready()).toBe(false);
    query.mockResolvedValueOnce({
      rows: [
        { status: 'pending', count: '2' },
        { status: 'dead', count: '1' },
        { status: 'delivered', count: '3' },
        { status: 'canceled', count: '4' },
        { status: 'unknown', count: '99' },
      ],
    });
    expect(await delivery.status()).toEqual({ pending: 2, dead: 1, delivered: 3, canceled: 4 });
  });
  it('requires authenticated scoped replay and passes retention cutoffs to the storage boundary', async () => {
    const { delivery, query } = fixture();
    expect(await delivery.replay('delivery', new ServerCallContext())).toBe(false);
    expect(query).not.toHaveBeenCalled();
    query.mockResolvedValueOnce({ rowCount: 1 });
    expect(
      await delivery.replay(
        'delivery',
        new ServerCallContext({ tenant: 'team', user: { userName: 'alice', isAuthenticated: true } }),
      ),
    ).toBe(true);
    expect(query.mock.calls[0][1]).toEqual(['delivery', 'team', 'alice']);
    expect(
      await delivery.replay('missing', new ServerCallContext({ user: { userName: 'alice', isAuthenticated: true } })),
    ).toBe(false);
    const cutoff = new Date('2020-01-01T00:00:00Z');
    query.mockResolvedValueOnce({ rowCount: 4 });
    expect(await delivery.prune(cutoff)).toBe(4);
    expect(query.mock.calls.at(-1)![1]).toEqual([cutoff]);
    expect(await delivery.prune(cutoff)).toBe(0);
    await expect(delivery.purgeTask('task', cutoff, new ServerCallContext(), 'tasks', 'push')).rejects.toThrow(
      'Authenticated',
    );
    await expect(
      delivery.purgeTask(
        'task',
        new Date('bad'),
        new ServerCallContext({ user: { userName: 'alice', isAuthenticated: true } }),
        'tasks',
        'push',
      ),
    ).rejects.toThrow('cutoff');
  });
  it('contains worker failures, stops rescheduling, and waits for the active claim before closing', async () => {
    vi.useFakeTimers();
    const { delivery, query } = fixture({ pollIntervalMs: 10 });
    query.mockRejectedValueOnce(new Error('offline'));
    delivery.start();
    await vi.advanceTimersByTimeAsync(10);
    expect(query.mock.calls.length).toBeGreaterThan(1);
    let finish!: (value: unknown) => void;
    query.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await vi.advanceTimersByTimeAsync(10);
    let stopped = false;
    const stopping = delivery.stop().then(() => {
      stopped = true;
    });
    await Promise.resolve();
    expect(stopped).toBe(false);
    finish({ rows: [], rowCount: 0 });
    await stopping;
    const count = query.mock.calls.length;
    await vi.advanceTimersByTimeAsync(100);
    expect(query).toHaveBeenCalledTimes(count);
  });
});

describe('explicit runtime migration lifecycle', () => {
  it('validates table identifiers and commits an explicit migration before releasing its connection', async () => {
    expect(runtimeTableNames()).toEqual({ outbox: 'a2a_lite_outbox', versions: 'a2a_lite_versions' });
    expect(() => runtimeTableNames('Bad-Name')).toThrow();
    const connection = { query: vi.fn().mockResolvedValue({ rows: [] }), release: vi.fn() };
    await migrateRuntimeTables({ connect: async () => connection } as unknown as pg.Pool);
    expect(connection.query.mock.calls[0][0]).toBe('BEGIN');
    expect(connection.query.mock.calls.at(-1)![0]).toBe('COMMIT');
    expect(connection.release).toHaveBeenCalledOnce();
  });
  it('rolls back failed migrations and always releases the connection', async () => {
    const connection = {
      query: vi.fn().mockResolvedValueOnce({}).mockRejectedValueOnce(new Error('DDL denied')).mockResolvedValue({}),
      release: vi.fn(),
    };
    await expect(
      migrateRuntimeTables({ connect: async () => connection } as unknown as pg.Pool, 'custom'),
    ).rejects.toThrow('DDL denied');
    expect(connection.query.mock.calls.at(-1)![0]).toBe('ROLLBACK');
    expect(connection.release).toHaveBeenCalledOnce();
  });
});
