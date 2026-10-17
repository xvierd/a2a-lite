import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { promisify } from 'node:util';
import { execFile } from 'node:child_process';
import { createRequire } from 'node:module';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import pg from 'pg';
import { ServerCallContext } from '@a2a-js/sdk/server';
import { TaskState, type Task } from '@a2a-js/sdk';
import { postWebhook } from '../src/push-delivery.js';
import request from 'supertest';
import { lookup } from 'node:dns/promises';
import { Agent, APIKeyAuth, TaskContext, createPostgresPersistence, migratePostgresRuntime } from '../src/index.js';

vi.mock('../src/push-delivery.js', async (original) => ({
  ...(await original<typeof import('../src/push-delivery.js')>()),
  postWebhook: vi.fn().mockResolvedValue(undefined),
}));
vi.mock('node:dns/promises', () => ({ lookup: vi.fn() }));
const dsn = process.env.A2ALITE_POSTGRES_DSN;
const prefix = 'ts_' + randomUUID().replaceAll('-', '').slice(0, 12);
const taskTable = prefix + '_tasks';
const pushTable = prefix + '_push';
const connect = () =>
  createPostgresPersistence({
    connectionString: dsn!,
    encryptionKey: Buffer.alloc(32, 7).toString('base64'),
    taskTable,
    pushTable,
  });
const auth = () =>
  new APIKeyAuth({
    identities: {
      old: { userId: 'alice', namespace: 'issuer', authorizedTenants: ['', 'a', 'b'] },
      rotated: { userId: 'alice', namespace: 'issuer', authorizedTenants: ['', 'a', 'b'] },
      other: { userId: 'bob', namespace: 'issuer', authorizedTenants: ['', 'a', 'b'] },
    },
  });

describe.skipIf(!dsn)('official PostgreSQL protocol stores', () => {
  beforeAll(async () => {
    const entry = createRequire(import.meta.url).resolve('@a2a-js/sdk');
    const cli = join(entry, '..', 'cli', 'a2a_db.js');
    const args = [cli, 'upgrade', '--tasks-table-name', taskTable, '--push-notification-configs-table-name', pushTable];
    await promisify(execFile)(process.execPath, args, { env: { ...process.env, DATABASE_URL: dsn } });
    // Migrations are explicitly repeatable.
    await promisify(execFile)(process.execPath, args, { env: { ...process.env, DATABASE_URL: dsn } });
    vi.mocked(lookup).mockResolvedValue([{ address: '93.184.216.34', family: 4 }] as never);
  });
  afterAll(async () => {
    const pool = new pg.Pool({ connectionString: dsn });
    for (const table of [
      taskTable,
      pushTable,
      prefix + '_outbox',
      prefix + '_versions',
      prefix + '_leases',
      prefix + '_journal',
      'a2a_' + taskTable + '_migrations',
      'a2a_' + pushTable + '_migrations',
    ])
      await pool.query(`DROP TABLE IF EXISTS ${table}`);
    await pool.end();
  });
  it('retains task and scoped callback configuration across close/reopen with rotation and tenant isolation', async () => {
    const persistence = await connect();
    expect(await persistence.ready()).toBe(true);
    const first = new Agent({
      name: 'Durable',
      description: 'SQL restart',
      auth: auth(),
      profile: 'durable',
      persistence,
    });
    first.skill('echo', { task: true }, async () => 'persisted');
    const runtime = await first.start({ host: '127.0.0.1', port: 0 });
    const rpc = (url: string, key: string, method: string, params: Record<string, unknown>) =>
      request(url)
        .post('/')
        .set('X-API-Key', key)
        .set('A2A-Version', '1.0')
        .send({ jsonrpc: '2.0', id: '1', method, params });
    const response = await rpc(runtime.url, 'old', 'SendMessage', {
      tenant: 'a',
      message: { messageId: 'm', role: 'ROLE_USER', parts: [{ text: '{"skill":"echo"}' }] },
    });
    expect(response.body.error).toBeUndefined();
    const id = response.body.result.task.id;
    const saved = await rpc(runtime.url, 'old', 'CreateTaskPushNotificationConfig', {
      tenant: 'a',
      taskId: id,
      id: randomUUID(),
      url: 'https://public.example/hook',
      token: 'opaque',
    });
    expect(saved.body.error).toBeUndefined();
    await runtime.stop();
    expect(await persistence.ready()).toBe(false);

    const second = new Agent({
      name: 'Durable',
      description: 'SQL restart',
      auth: auth(),
      profile: 'durable',
      persistence: await connect(),
    });
    const restarted = await second.start({ host: '127.0.0.1', port: 0 });
    try {
      expect((await rpc(restarted.url, 'rotated', 'GetTask', { id, tenant: 'a' })).body.result.id).toBe(id);
      expect(
        (await rpc(restarted.url, 'rotated', 'ListTaskPushNotificationConfigs', { taskId: id, tenant: 'a' })).body
          .result.configs[0].token,
      ).toBe('opaque');
      for (const [key, tenant] of [
        ['other', 'a'],
        ['rotated', 'b'],
      ]) {
        expect((await rpc(restarted.url, key, 'GetTask', { id, tenant })).body.error.code).toBe(-32001);
        expect((await rpc(restarted.url, key, 'ListTasks', { tenant })).body.result.tasks ?? []).toEqual([]);
        expect(
          (await rpc(restarted.url, key, 'ListTaskPushNotificationConfigs', { taskId: id, tenant })).body.error.code,
        ).toBe(-32001);
      }
    } finally {
      await restarted.stop();
    }
  });
  it('fails readiness/startup for missing migrations without leaving a pool open', async () => {
    const persistence = await createPostgresPersistence({
      connectionString: dsn!,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      taskTable: prefix + '_missing',
      pushTable,
    });
    expect(await persistence.ready()).toBe(false);
    const agent = new Agent({
      name: 'Missing',
      description: 'Missing migration',
      auth: auth(),
      profile: 'durable',
      persistence,
    });
    await expect(agent.start({ host: '127.0.0.1', port: 0 })).rejects.toThrow('storage is not ready');
    expect(await persistence.ready()).toBe(false);
  });
  it('atomically rolls back state when the outbox cannot accept all subscription events', async () => {
    await migratePostgresRuntime({ connectionString: dsn!, delivery: { tablePrefix: prefix } });
    const persistence = await createPostgresPersistence({
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix, maxPending: 1 },
    });
    const context = new ServerCallContext({
      user: { userName: 'atomic', isAuthenticated: true },
      requestedVersion: '1.0',
    });
    const id = randomUUID();
    for (const configId of [randomUUID(), randomUUID()])
      await persistence.pushStore.save(id, context, {
        taskId: id,
        id: configId,
        url: 'https://public.example/hook',
        token: 'private-token',
        authentication: undefined,
      });
    const task: Task = {
      id,
      contextId: randomUUID(),
      status: { state: TaskState.TASK_STATE_COMPLETED, timestamp: new Date().toISOString(), message: undefined },
      history: [],
      artifacts: [],
      metadata: undefined,
    };
    await expect(persistence.taskStore.save(task, context)).rejects.toThrow('capacity');
    expect(await persistence.taskStore.load(id, context)).toBeUndefined();
    expect((await persistence.delivery!.status()).pending).toBe(0);
    await persistence.close();
  });
  it('retains delivery IDs through retry/restart, encrypts credentials, and authorizes replay', async () => {
    const options = {
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix, maxAttempts: 1, retryBaseMs: 1 },
    };
    let persistence = await createPostgresPersistence(options);
    const context = new ServerCallContext({
      user: { userName: 'delivery', isAuthenticated: true },
      requestedVersion: '1.0',
    });
    const id = randomUUID();
    await persistence.pushStore.save(id, context, {
      taskId: id,
      id: randomUUID(),
      url: 'https://public.example/hook',
      token: 'private-token',
      authentication: undefined,
    });
    await persistence.taskStore.save(
      {
        id,
        contextId: randomUUID(),
        status: { state: TaskState.TASK_STATE_COMPLETED, timestamp: new Date().toISOString(), message: undefined },
        history: [],
        artifacts: [],
        metadata: undefined,
      },
      context,
    );
    const pool = new pg.Pool({ connectionString: dsn });
    const stored = await pool.query(`SELECT config_data FROM ${pushTable} WHERE owner='delivery'`);
    expect(JSON.stringify(stored.rows)).not.toContain('private-token');
    await persistence.close();
    persistence = await createPostgresPersistence(options);
    vi.mocked(postWebhook)
      .mockReset()
      .mockRejectedValueOnce(new Error('temporary callback failure'))
      .mockResolvedValue(undefined);
    await persistence.delivery!.dispatchOnce();
    const deliveryId = vi.mocked(postWebhook).mock.calls[0][1].headers['X-A2A-Delivery-Id'];
    expect((await persistence.delivery!.status()).dead).toBe(1);
    expect(
      await persistence.delivery!.replay(
        deliveryId,
        new ServerCallContext({ user: { userName: 'other', isAuthenticated: true } }),
      ),
    ).toBe(false);
    expect(await persistence.delivery!.replay(deliveryId, context)).toBe(true);
    await persistence.delivery!.dispatchOnce();
    expect(vi.mocked(postWebhook).mock.calls[1][1].headers).toMatchObject({
      'X-A2A-Delivery-Id': deliveryId,
      'X-A2A-Notification-Token': 'private-token',
    });
    expect((await persistence.delivery!.status()).delivered).toBe(1);
    await persistence.close();
    await pool.end();
  });
  it('rejects a stale cross-connection state writer without overwriting the committed task', async () => {
    const options = {
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix },
    };
    const one = await createPostgresPersistence(options);
    const two = await createPostgresPersistence(options);
    const context = () =>
      new ServerCallContext({ user: { userName: 'writer', isAuthenticated: true }, requestedVersion: '1.0' });
    const first = context();
    const stale = context();
    const id = randomUUID();
    const task: Task = {
      id,
      contextId: randomUUID(),
      status: { state: TaskState.TASK_STATE_WORKING, timestamp: new Date().toISOString(), message: undefined },
      history: [],
      artifacts: [],
      metadata: undefined,
    };
    await one.taskStore.save(task, first);
    await one.taskStore.load(id, first);
    await two.taskStore.load(id, stale);
    await one.taskStore.save({ ...task, status: { ...task.status!, state: TaskState.TASK_STATE_CANCELED } }, first);
    await expect(
      two.taskStore.save({ ...task, status: { ...task.status!, state: TaskState.TASK_STATE_COMPLETED } }, stale),
    ).rejects.toThrow('Concurrent task update');
    expect((await two.taskStore.load(id, stale))!.status!.state).toBe(TaskState.TASK_STATE_CANCELED);
    await one.close();
    await two.close();
  });
  it('routes subscription and cancellation from a second replica and fences the first executor', async () => {
    const options = {
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix },
      execution: { leaseMs: 15000, pollIntervalMs: 50 },
    };
    const one = new Agent({
      name: 'One',
      description: 'Replica',
      auth: auth(),
      profile: 'durable',
      persistence: await createPostgresPersistence(options),
    });
    const two = new Agent({
      name: 'Two',
      description: 'Replica',
      auth: auth(),
      profile: 'durable',
      persistence: await createPostgresPersistence(options),
    });
    let aborted = false;
    const handler = async function* ({ task }: Record<string, unknown>) {
      const context = task as TaskContext;
      context.signal.addEventListener(
        'abort',
        () => {
          aborted = true;
        },
        { once: true },
      );
      for (let index = 0; index < 400; index++) {
        await new Promise((resolve) => setTimeout(resolve, 25));
        context.signal.throwIfAborted();
        yield String(index);
      }
    };
    one.skill('hold', { streaming: true, taskContext: true }, handler);
    two.skill('hold', { streaming: true, taskContext: true }, handler);
    const a = await one.start({ host: '127.0.0.1', port: 0 });
    const b = await two.start({ host: '127.0.0.1', port: 0 });
    const rpc = (url: string, method: string, params: Record<string, unknown>) =>
      request(url)
        .post('/')
        .set('X-API-Key', 'old')
        .set('A2A-Version', '1.0')
        .send({ jsonrpc: '2.0', id: '1', method, params });
    try {
      const original = await fetch(a.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': 'old', 'A2A-Version': '1.0' },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 'original',
          method: 'SendStreamingMessage',
          params: { message: { messageId: 'm', role: 'ROLE_USER', parts: [{ text: '{"skill":"hold"}' }] } },
        }),
        signal: AbortSignal.timeout(5000),
      });
      const originalReader = original.body!.getReader();
      let originalEvents = new TextDecoder().decode((await originalReader.read()).value);
      const id = JSON.parse(
        originalEvents
          .split('\n')
          .find((line) => line.startsWith('data:'))!
          .slice(5),
      ).result.task.id;
      expect((await rpc(b.url, 'GetTask', { id })).body.result.id).toBe(id);
      const stream = await fetch(b.url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': 'old', 'A2A-Version': '1.0' },
        body: JSON.stringify({ jsonrpc: '2.0', id: '2', method: 'SubscribeToTask', params: { id } }),
        signal: AbortSignal.timeout(3000),
      });
      const reader = stream.body!.getReader();
      let events = new TextDecoder().decode((await reader.read()).value);
      const canceled = await rpc(b.url, 'CancelTask', { id });
      expect(canceled.body.error).toBeUndefined();
      expect(canceled.body.result.status.state).toBe('TASK_STATE_CANCELED');
      while (!events.includes('TASK_STATE_CANCELED')) {
        const next = await reader.read();
        if (next.done) break;
        events += new TextDecoder().decode(next.value);
      }
      expect(events).toContain('TASK_STATE_CANCELED');
      await reader.cancel();
      while (!originalEvents.includes('TASK_STATE_CANCELED')) {
        const next = await originalReader.read();
        if (next.done) break;
        originalEvents += new TextDecoder().decode(next.value);
      }
      expect(originalEvents).toContain('TASK_STATE_CANCELED');
      await originalReader.cancel();
      await vi.waitFor(() => expect(aborted).toBe(true));
      expect((await rpc(b.url, 'GetTask', { id })).body.result.status.state).toBe('TASK_STATE_CANCELED');
    } finally {
      await Promise.all([a.stop(), b.stop()]);
    }
  });
  it('recovers an explicitly checkpointed lease and rejects the stale holder', async () => {
    const options = {
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix },
      execution: { leaseMs: 1000, pollIntervalMs: 50 },
    };
    const one = await createPostgresPersistence(options);
    const two = await createPostgresPersistence(options);
    const context = () =>
      new ServerCallContext({ user: { userName: 'checkpoint', isAuthenticated: true }, requestedVersion: '1.0' });
    const old = context();
    const fresh = context();
    const id = randomUUID();
    const lease = await one.execution!.acquire(id, old);
    await lease.checkpoint({ next: 7, idempotencyKey: 'example-job' });
    const pool = new pg.Pool({ connectionString: dsn });
    await pool.query(`UPDATE ${prefix}_leases SET lease_until=now()-interval '1 second' WHERE task_id=$1`, [id]);
    const replacement = await two.execution!.acquire(id, fresh);
    expect(replacement.checkpointData).toEqual({ next: 7, idempotencyKey: 'example-job' });
    await expect(lease.checkpoint({ next: 8 })).rejects.toThrow();
    await expect(
      one.taskStore.save(
        {
          id,
          contextId: randomUUID(),
          status: { state: TaskState.TASK_STATE_COMPLETED, timestamp: new Date().toISOString(), message: undefined },
          history: [],
          artifacts: [],
          metadata: undefined,
        },
        old,
      ),
    ).rejects.toThrow('Stale execution fence');
    await replacement.release();
    await one.close();
    await two.close();
    await pool.end();
  });
  it('settles accepted task cancellation before closing PostgreSQL during shutdown', async () => {
    const options = {
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix },
      execution: {},
    };
    const persistence = await createPostgresPersistence(options);
    const agent = new Agent({
      name: 'Drain',
      description: 'Shutdown settlement',
      auth: auth(),
      profile: 'durable',
      persistence,
    });
    agent.skill('wait', { task: true, taskContext: true }, async ({ task }) => {
      const context = task as TaskContext;
      await new Promise((resolve) => context.signal.addEventListener('abort', resolve, { once: true }));
      return 'late';
    });
    const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
    const response = await request(runtime.url)
      .post('/')
      .set('X-API-Key', 'old')
      .set('A2A-Version', '1.0')
      .send({
        jsonrpc: '2.0',
        id: '1',
        method: 'SendMessage',
        params: {
          configuration: { returnImmediately: true },
          message: { messageId: 'm', role: 'ROLE_USER', parts: [{ text: '{"skill":"wait"}' }] },
        },
      });
    const id = response.body.result.task.id;
    await runtime.stop();
    const reopened = await createPostgresPersistence(options);
    const identity = await auth().authenticate({ headers: { 'x-api-key': 'old' } });
    const { principalKey } = await import('../src/authorization.js');
    const task = await reopened.taskStore.load(
      id,
      new ServerCallContext({
        user: { userName: principalKey(identity.userId!, identity.namespace), isAuthenticated: true },
      }),
    );
    expect(task!.status!.state).toBe(TaskState.TASK_STATE_CANCELED);
    await reopened.close();
  });
  it('claims each callback once across two workers and rejects a tampered credential binding', async () => {
    const options = {
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix },
    };
    const one = await createPostgresPersistence(options);
    const two = await createPostgresPersistence(options);
    const context = new ServerCallContext({
      user: { userName: 'workers', isAuthenticated: true },
      requestedVersion: '1.0',
    });
    const id = randomUUID();
    await one.pushStore.save(id, context, {
      taskId: id,
      id: randomUUID(),
      url: 'https://public.example/hook',
      token: 'worker-secret',
      authentication: undefined,
    });
    await one.taskStore.save(
      {
        id,
        contextId: randomUUID(),
        status: { state: TaskState.TASK_STATE_COMPLETED, timestamp: new Date().toISOString(), message: undefined },
        history: [],
        artifacts: [],
        metadata: undefined,
      },
      context,
    );
    vi.mocked(postWebhook).mockReset().mockResolvedValue(undefined);
    const claims = await Promise.all([one.delivery!.dispatchOnce(), two.delivery!.dispatchOnce()]);
    expect(claims.filter(Boolean)).toHaveLength(1);
    expect(postWebhook).toHaveBeenCalledOnce();
    const pool = new pg.Pool({ connectionString: dsn });
    const rows = await pool.query(`SELECT config_data FROM ${pushTable} WHERE owner='workers'`);
    const data = JSON.parse(rows.rows[0].config_data);
    data.url = 'https://changed.example/hook';
    await pool.query(`UPDATE ${pushTable} SET config_data=$1 WHERE owner='workers'`, [JSON.stringify(data)]);
    await expect(one.pushStore.load(id, context)).rejects.toThrow();
    await one.close();
    await two.close();
    await pool.end();
  });
  it('rotates callback credentials by key ID and reads restored legacy ciphertext with retained keys', async () => {
    const legacy = Buffer.alloc(32, 7).toString('base64');
    const named = Buffer.alloc(32, 9).toString('base64');
    const options = { connectionString: dsn!, taskTable, pushTable };
    let persistence = await createPostgresPersistence({ ...options, encryptionKey: legacy });
    const context = new ServerCallContext({ tenant: 'rotation', user: { userName: 'alice', isAuthenticated: true } });
    const id = randomUUID();
    await persistence.taskStore.save(
      {
        id,
        contextId: randomUUID(),
        status: { state: TaskState.TASK_STATE_COMPLETED, timestamp: new Date().toISOString(), message: undefined },
        history: [],
        artifacts: [],
        metadata: undefined,
      },
      context,
    );
    await persistence.pushStore.save(id, context, {
      taskId: id,
      id: 'hook',
      url: 'https://public.example/hook',
      token: 'rotated-token',
      authentication: { scheme: 'Bearer', credentials: 'rotated-auth' },
    });
    const pool = new pg.Pool({ connectionString: dsn });
    const backup = (await pool.query(`SELECT config_data FROM ${pushTable} WHERE task_id=$1`, [id])).rows[0]
      .config_data;
    expect(backup).toContain('a2a-enc:v1:');
    await persistence.close();
    const keys = { encryptionKey: legacy, encryptionKeys: { blue: named }, activeEncryptionKeyId: 'blue' };
    persistence = await createPostgresPersistence({ ...options, ...keys });
    await expect(persistence.rotateCallbackCredentials!(id, new ServerCallContext())).rejects.toThrow('Authenticated');
    await expect(
      persistence.rotateCallbackCredentials!(
        id,
        new ServerCallContext({ user: { userName: 'bob', isAuthenticated: true } }),
      ),
    ).rejects.toThrow('Task not found');
    expect(await persistence.rotateCallbackCredentials!(id, context)).toBe(1);
    const encrypted = (await pool.query(`SELECT config_data FROM ${pushTable} WHERE task_id=$1`, [id])).rows[0]
      .config_data;
    expect(encrypted).toContain('a2a-enc:v2:blue:');
    expect(encrypted).not.toContain('rotated-token');
    await persistence.close();
    persistence = await createPostgresPersistence({
      ...options,
      encryptionKeys: { blue: named },
      activeEncryptionKeyId: 'blue',
    });
    expect((await persistence.pushStore.load(id, context))[0]).toMatchObject({
      token: 'rotated-token',
      authentication: { credentials: 'rotated-auth' },
    });
    await pool.query(`UPDATE ${pushTable} SET config_data=$1 WHERE task_id=$2`, [backup, id]);
    await expect(persistence.pushStore.load(id, context)).rejects.toThrow('key is unavailable');
    await persistence.close();
    persistence = await createPostgresPersistence({ ...options, ...keys });
    expect((await persistence.pushStore.load(id, context))[0].token).toBe('rotated-token');
    expect(await persistence.rotateCallbackCredentials!(id, context)).toBe(1);
    await persistence.close();
    await pool.end();
  });
  it('purges only scoped terminal payloads without pending deliveries and fences stale resurrection', async () => {
    const persistence = await createPostgresPersistence({
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix },
    });
    const context = new ServerCallContext({ tenant: 'retention', user: { userName: 'owner', isAuthenticated: true } });
    const id = randomUUID();
    const task: Task = {
      id,
      contextId: randomUUID(),
      status: {
        state: TaskState.TASK_STATE_COMPLETED,
        timestamp: new Date(Date.now() - 1000).toISOString(),
        message: undefined,
      },
      history: [],
      artifacts: [],
      metadata: undefined,
    };
    await persistence.pushStore.save(id, context, {
      taskId: id,
      id: 'hook',
      url: 'https://public.example/hook',
      token: 'secret',
      authentication: undefined,
    });
    await persistence.taskStore.save(task, context);
    const stale = new ServerCallContext({ tenant: 'retention', user: { userName: 'owner', isAuthenticated: true } });
    await persistence.taskStore.load(id, stale);
    expect(await persistence.purgeTask!(id, new Date(), context)).toBe(false);
    vi.mocked(postWebhook).mockReset().mockResolvedValue(undefined);
    await persistence.delivery!.dispatchOnce();
    expect(
      await persistence.purgeTask!(
        id,
        new Date(),
        new ServerCallContext({ tenant: 'other', user: { userName: 'owner', isAuthenticated: true } }),
      ),
    ).toBe(false);
    expect(await persistence.purgeTask!(id, new Date(), context)).toBe(true);
    expect(await persistence.taskStore.load(id, context)).toBeUndefined();
    expect(await persistence.pushStore.load(id, context)).toEqual([]);
    await expect(persistence.taskStore.save(task, stale)).rejects.toThrow('purged');
    const pool = new pg.Pool({ connectionString: dsn });
    for (const table of [prefix + '_outbox', prefix + '_journal', prefix + '_leases'])
      expect((await pool.query(`SELECT count(*) FROM ${table} WHERE task_id=$1`, [id])).rows[0].count).toBe('0');
    await pool.end();
    await persistence.close();
  });
  it('expires aged or crash-exhausted callback claims without retrying externally', async () => {
    const persistence = await createPostgresPersistence({
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix, maxAttempts: 2, maxAgeMs: 1000 },
    });
    const context = new ServerCallContext({ user: { userName: 'expired-delivery', isAuthenticated: true } });
    const pool = new pg.Pool({ connectionString: dsn });
    const ids = [randomUUID(), randomUUID()];
    for (const id of ids) {
      await persistence.pushStore.save(id, context, {
        taskId: id,
        id: 'hook',
        url: 'https://public.example/hook',
        token: 'secret',
        authentication: undefined,
      });
      await persistence.taskStore.save(
        {
          id,
          contextId: randomUUID(),
          status: { state: TaskState.TASK_STATE_COMPLETED, timestamp: new Date().toISOString(), message: undefined },
          history: [],
          artifacts: [],
          metadata: undefined,
        },
        context,
      );
    }
    await pool.query(`UPDATE ${prefix}_outbox SET attempts=2,lease_until=now()-interval '1 second' WHERE task_id=$1`, [
      ids[0],
    ]);
    await pool.query(`UPDATE ${prefix}_outbox SET created_at=now()-interval '2 seconds' WHERE task_id=$1`, [ids[1]]);
    vi.mocked(postWebhook).mockReset().mockResolvedValue(undefined);
    expect(await persistence.delivery!.dispatchOnce()).toBe(true);
    expect(postWebhook).not.toHaveBeenCalled();
    const rows = (await pool.query(`SELECT id,status FROM ${prefix}_outbox WHERE owner='expired-delivery'`)).rows;
    expect(rows.map((row) => row.status)).toEqual(['dead', 'dead']);
    expect(await persistence.delivery!.replay(rows[1].id, context)).toBe(true);
    await persistence.delivery!.dispatchOnce();
    expect(postWebhook).toHaveBeenCalledOnce();
    expect(vi.mocked(postWebhook).mock.calls[0][1].headers['X-A2A-Delivery-Id']).toBe(rows[1].id);
    await persistence.close();
    await pool.end();
  });
  it('reconciles expired execution atomically and retains explicit checkpoints for manual continuation', async () => {
    const persistence = await createPostgresPersistence({
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix },
      execution: { leaseMs: 15000 },
    });
    const pool = new pg.Pool({ connectionString: dsn });
    for (const checkpointed of [false, true]) {
      const id = randomUUID();
      const context = new ServerCallContext({ user: { userName: 'crash', isAuthenticated: true } });
      const lease = await persistence.execution!.acquire(id, context);
      await persistence.taskStore.save(
        {
          id,
          contextId: randomUUID(),
          status: { state: TaskState.TASK_STATE_WORKING, timestamp: new Date().toISOString(), message: undefined },
          history: [],
          artifacts: [],
          metadata: undefined,
        },
        context,
      );
      if (checkpointed) await lease.checkpoint({ next: 3 });
      await pool.query(`UPDATE ${prefix}_leases SET lease_until=now()-interval '1 second' WHERE task_id=$1`, [id]);
      expect(await persistence.execution!.reconcileExpiredTasks()).toBe(1);
      const read = new ServerCallContext({ user: { userName: 'crash', isAuthenticated: true } });
      const task = await persistence.taskStore.load(id, read);
      expect(task!.status!.state).toBe(
        checkpointed ? TaskState.TASK_STATE_INPUT_REQUIRED : TaskState.TASK_STATE_FAILED,
      );
      await expect(lease.checkpoint({ next: 4 })).rejects.toThrow();
      expect(await persistence.execution!.reconcileExpiredTasks()).toBe(0);
      if (checkpointed) {
        const resumed = await persistence.execution!.acquire(id, read);
        expect(resumed.checkpointData).toEqual({ next: 3 });
        await resumed.release();
      }
    }
    await persistence.close();
    await pool.end();
  });
  it('continues an INPUT_REQUIRED task on another replica with the rotated owner identity', async () => {
    const options = {
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix },
      execution: {},
    };
    const agents = await Promise.all(
      [1, 2].map(async (index) => {
        const agent = new Agent({
          name: 'Pause' + index,
          description: 'Continuation',
          auth: auth(),
          profile: 'durable',
          persistence: await createPostgresPersistence(options),
        });
        agent.skill('pause', { task: true, taskContext: true }, async ({ task, resume }) => {
          if (resume === true) return 'resumed';
          await (task as TaskContext).update('input-required');
          return undefined;
        });
        return agent.start({ host: '127.0.0.1', port: 0 });
      }),
    );
    const send = (url: string, key: string, id?: string) =>
      request(url)
        .post('/')
        .set('X-API-Key', key)
        .set('A2A-Version', '1.0')
        .send({
          jsonrpc: '2.0',
          id: '1',
          method: 'SendMessage',
          params: {
            tenant: 'a',
            message: {
              messageId: randomUUID(),
              taskId: id,
              role: 'ROLE_USER',
              parts: [{ text: JSON.stringify({ skill: 'pause', params: { resume: !!id } }) }],
            },
          },
        });
    try {
      const initial = await send(agents[0].url, 'old');
      expect(initial.body.result.task.status.state).toBe('TASK_STATE_INPUT_REQUIRED');
      const id = initial.body.result.task.id;
      expect((await send(agents[1].url, 'other', id)).body.error).toBeDefined();
      const resumed = await send(agents[1].url, 'rotated', id);
      expect(resumed.body.error).toBeUndefined();
      expect(resumed.body.result.task.id).toBe(id);
      expect(resumed.body.result.task.status.state).toBe('TASK_STATE_COMPLETED');
      expect(resumed.body.result.task.artifacts.at(-1).parts[0].text).toBe('resumed');
    } finally {
      await Promise.all(agents.map((runtime) => runtime.stop()));
    }
  });
  it('cancels queued attempts on config deletion even when its ID is recreated, and sends both auth headers', async () => {
    const persistence = await createPostgresPersistence({
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix, autoStart: false },
    });
    const context = new ServerCallContext({ user: { userName: 'delete-config', isAuthenticated: true } });
    const id = randomUUID();
    const config = {
      taskId: id,
      id: 'hook',
      url: 'https://public.example/old',
      token: 'old-token',
      authentication: { scheme: 'Bearer', credentials: 'old-auth' },
    };
    const task: Task = {
      id,
      contextId: randomUUID(),
      status: { state: TaskState.TASK_STATE_WORKING, timestamp: new Date().toISOString(), message: undefined },
      history: [],
      artifacts: [],
      metadata: undefined,
    };
    await persistence.pushStore.save(id, context, config);
    await persistence.taskStore.save(task, context);
    await persistence.pushStore.delete(id, context, config.id);
    await persistence.pushStore.save(id, context, {
      ...config,
      url: 'https://public.example/new',
      token: 'new-token',
      authentication: { scheme: 'Bearer', credentials: 'new-auth' },
    });
    vi.mocked(postWebhook).mockReset().mockResolvedValue(undefined);
    persistence.start!();
    expect(await persistence.delivery!.dispatchOnce()).toBe(false);
    expect(postWebhook).not.toHaveBeenCalled();
    await persistence.taskStore.save(
      { ...task, status: { ...task.status!, state: TaskState.TASK_STATE_COMPLETED } },
      context,
    );
    expect(await persistence.delivery!.dispatchOnce()).toBe(true);
    expect(postWebhook).toHaveBeenCalledOnce();
    expect(vi.mocked(postWebhook).mock.calls[0][0]).toBe('https://public.example/new');
    expect(vi.mocked(postWebhook).mock.calls[0][1].headers).toMatchObject({
      Authorization: 'Bearer new-auth',
      'X-A2A-Notification-Token': 'new-token',
    });
    const pool = new pg.Pool({ connectionString: dsn });
    const canceled = (await pool.query(`SELECT id FROM ${prefix}_outbox WHERE task_id=$1 AND status='canceled'`, [id]))
      .rows;
    expect(canceled).toHaveLength(1);
    expect(await persistence.delivery!.replay(canceled[0].id, context)).toBe(false);
    await pool.end();
    await persistence.close();
  });
  it('treats REJECTED as terminal for cancellation and state writes', async () => {
    const persistence = await createPostgresPersistence({
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix },
      execution: {},
    });
    const context = new ServerCallContext({ user: { userName: 'rejected', isAuthenticated: true } });
    const id = randomUUID();
    const task: Task = {
      id,
      contextId: randomUUID(),
      status: { state: TaskState.TASK_STATE_REJECTED, timestamp: new Date().toISOString(), message: undefined },
      history: [],
      artifacts: [],
      metadata: undefined,
    };
    await persistence.taskStore.save(task, context);
    await expect(persistence.execution!.cancelTask(id, context)).rejects.toThrow();
    await expect(
      persistence.taskStore.save(
        { ...task, status: { ...task.status!, state: TaskState.TASK_STATE_COMPLETED } },
        context,
      ),
    ).rejects.toThrow('Terminal');
    expect((await persistence.taskStore.load(id, context))!.status!.state).toBe(TaskState.TASK_STATE_REJECTED);
    await persistence.close();
  });
  it('does not allocate execution lease rows for ordinary Message calls', async () => {
    const persistence = await createPostgresPersistence({
      connectionString: dsn!,
      taskTable,
      pushTable,
      encryptionKey: Buffer.alloc(32, 7).toString('base64'),
      delivery: { tablePrefix: prefix, autoStart: false },
      execution: {},
    });
    const agent = new Agent({
      name: 'Messages',
      description: 'No durable execution',
      profile: 'durable',
      persistence,
      auth: new APIKeyAuth({ identities: { key: 'message-owner' } }),
    });
    agent.skill('greet', async () => 'hello');
    const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
    try {
      for (let index = 0; index < 5; index++) {
        const response = await request(runtime.url)
          .post('/')
          .set('X-API-Key', 'key')
          .set('A2A-Version', '1.0')
          .send({
            jsonrpc: '2.0',
            id: String(index),
            method: 'SendMessage',
            params: { message: { messageId: randomUUID(), role: 'ROLE_USER', parts: [{ text: '{"skill":"greet"}' }] } },
          });
        expect(response.body.result.message.parts[0].text).toBe('hello');
      }
      const pool = new pg.Pool({ connectionString: dsn });
      expect(
        (await pool.query(`SELECT count(*) FROM ${prefix}_leases WHERE owner='message-owner'`)).rows[0].count,
      ).toBe('0');
      await pool.end();
    } finally {
      await runtime.stop();
    }
  });
});
