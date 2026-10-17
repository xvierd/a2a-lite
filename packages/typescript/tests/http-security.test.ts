import request from 'supertest';
import type { Express } from 'express';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { lookup } from 'node:dns/promises';
import { Agent, BearerAuth, CompositeAuth, NoAuth } from '../src/index.js';
import { postWebhook } from '../src/push-delivery.js';

vi.mock('node:dns/promises', () => ({ lookup: vi.fn() }));
vi.mock('../src/push-delivery.js', async (original) => ({
  ...(await original<typeof import('../src/push-delivery.js')>()),
  postWebhook: vi.fn().mockResolvedValue(undefined),
}));

function rpc(app: Express, user: string, method: string, params: Record<string, unknown>) {
  return request(app)
    .post('/')
    .set('Authorization', `Bearer ${user}`)
    .set('A2A-Version', '1.0')
    .send({ jsonrpc: '2.0', id: 'request-1', method, params });
}

async function createTask(app: Express, user: string, tenant = ''): Promise<string> {
  const response = await rpc(app, user, 'SendMessage', {
    tenant,
    message: {
      messageId: 'message-1',
      role: 'ROLE_USER',
      parts: [{ text: JSON.stringify({ skill: 'count', params: {} }) }],
    },
  }).expect(200);
  expect(response.body.error).toBeUndefined();
  return response.body.result.task.id;
}

describe('authenticated SDK task and push isolation', () => {
  let app: Express;
  beforeEach(() => {
    vi.mocked(lookup)
      .mockReset()
      .mockResolvedValue([{ address: '93.184.216.34', family: 4 }] as never);
    vi.mocked(postWebhook).mockClear();
    const agent = new Agent({
      name: 'OwnedTasks',
      description: 'Scoped protocol tests',
      auth: new BearerAuth({ validator: (token) => (['alice', 'bob'].includes(token) ? token : null) }),
    });
    agent.skill('count', { streaming: true }, async function* () {
      yield 'one';
    });
    app = agent.buildApp();
  });

  it('scopes task reads, list, cancel and follow-up to the authenticated owner', async () => {
    const id = await createTask(app, 'alice');
    expect((await rpc(app, 'alice', 'GetTask', { id })).body.result.id).toBe(id);
    for (const method of ['GetTask', 'CancelTask', 'SubscribeToTask']) {
      expect((await rpc(app, 'bob', method, { id })).body.error.code).toBe(-32001);
    }
    const listed = await rpc(app, 'bob', 'ListTasks', {});
    expect(listed.body.result.tasks ?? []).toEqual([]);
    const continued = await rpc(app, 'bob', 'SendMessage', {
      message: { messageId: 'followup', taskId: id, role: 'ROLE_USER', parts: [{ text: 'count' }] },
    });
    expect(continued.body.error.code).toBe(-32001);
  });

  it('propagates the same identity to REST and preserves tenant isolation', async () => {
    const id = await createTask(app, 'alice', 'tenant-a');
    await request(app)
      .get(`/tenant-a/tasks/${id}`)
      .set('Authorization', 'Bearer alice')
      .set('A2A-Version', '1.0')
      .expect(200);
    await request(app)
      .get(`/tenant-a/tasks/${id}`)
      .set('Authorization', 'Bearer bob')
      .set('A2A-Version', '1.0')
      .expect(404);
    expect((await rpc(app, 'alice', 'GetTask', { id, tenant: 'tenant-b' })).body.error.code).toBe(-32001);
  });

  it('requires authentication and task ownership before accepting callback configuration', async () => {
    const id = await createTask(app, 'alice');
    for (const [user, taskId] of [
      ['alice', 'missing'],
      ['bob', id],
      ['invalid', id],
    ]) {
      const response = await rpc(app, user, 'CreateTaskPushNotificationConfig', {
        taskId,
        id: 'callback',
        url: 'https://public.example/hook',
      });
      expect(response.status).toBe(user === 'invalid' ? 401 : 200);
      expect(response.body.error).toBeDefined();
    }
    expect(lookup).not.toHaveBeenCalled();
    expect(postWebhook).not.toHaveBeenCalled();
  });

  it('isolates multiple callback IDs, users and tenants, including REST configuration', async () => {
    const taskId = await createTask(app, 'alice');
    for (const id of ['first', 'second']) {
      const response = await rpc(app, 'alice', 'CreateTaskPushNotificationConfig', {
        taskId,
        id,
        url: `https://public.example/${id}`,
        token: id,
      });
      expect(response.body.result.id).toBe(id);
    }
    for (const method of [
      'GetTaskPushNotificationConfig',
      'DeleteTaskPushNotificationConfig',
      'ListTaskPushNotificationConfigs',
    ]) {
      expect((await rpc(app, 'bob', method, { taskId, id: 'first' })).body.error.code).toBe(-32001);
      expect((await rpc(app, 'alice', method, { taskId, id: 'first', tenant: 'another' })).body.error.code).toBe(
        -32001,
      );
    }
    const get = await rpc(app, 'alice', 'GetTaskPushNotificationConfig', { taskId, id: 'second' });
    expect(get.body.result.token).toBe('second');
    await rpc(app, 'alice', 'DeleteTaskPushNotificationConfig', { taskId, id: 'first' });
    const list = await rpc(app, 'alice', 'ListTaskPushNotificationConfigs', { taskId });
    expect(list.body.result.configs.map((config: { id: string }) => config.id)).toEqual(['second']);
    const rest = await request(app)
      .get(`/tasks/${taskId}/pushNotificationConfigs/second`)
      .set('Authorization', 'Bearer alice')
      .set('A2A-Version', '1.0')
      .expect(200);
    expect(rest.body.id).toBe('second');
  });

  it.each([
    'http://public.example/hook',
    'https://127.0.0.1/hook',
    'https://169.254.169.254/',
    'https://[::1]/',
    'file:///tmp/hook',
    'https://user:secret@public.example/hook',
  ])('rejects unsafe registered callbacks: %s', async (url) => {
    const taskId = await createTask(app, 'alice');
    const response = await rpc(app, 'alice', 'CreateTaskPushNotificationConfig', { taskId, id: 'unsafe', url });
    expect(response.body.error).toBeDefined();
    const list = await rpc(app, 'alice', 'ListTaskPushNotificationConfigs', { taskId });
    expect(list.body.result.configs ?? []).toEqual([]);
    expect(postWebhook).not.toHaveBeenCalled();
  });

  it('validates inline SendMessage callback configuration before invoking a skill', async () => {
    const response = await rpc(app, 'alice', 'SendMessage', {
      configuration: { taskPushNotificationConfig: { id: 'inline', url: 'http://127.0.0.1/hook' } },
      message: { messageId: 'inline', role: 'ROLE_USER', parts: [{ text: '{"skill":"count"}' }] },
    });
    expect(response.body.error).toBeDefined();
    const listed = await rpc(app, 'alice', 'ListTasks', {});
    expect(listed.body.result.tasks ?? []).toEqual([]);
    expect(postWebhook).not.toHaveBeenCalled();
  });

  it('delivers inline protocol notifications using v1.0 envelopes and token headers', async () => {
    const response = await rpc(app, 'alice', 'SendMessage', {
      configuration: {
        taskPushNotificationConfig: { id: 'inline', url: 'https://public.example/hook', token: 'opaque-token' },
      },
      message: { messageId: 'inline', role: 'ROLE_USER', parts: [{ text: '{"skill":"count"}' }] },
    });
    expect(response.body.result.task).toBeDefined();
    await vi.waitFor(() => expect(postWebhook).toHaveBeenCalled());
    const [, options] = vi.mocked(postWebhook).mock.calls[0];
    expect(options.headers).toMatchObject({
      'Content-Type': 'application/a2a+json',
      'X-A2A-Notification-Token': 'opaque-token',
    });
    expect(JSON.parse(options.body).task.id).toBe(response.body.result.task.id);
  });
});

describe('authentication failures', () => {
  it.each([undefined, new CompositeAuth([new BearerAuth({ validator: () => null }), new NoAuth()])])(
    'keeps NoAuth tasks public while rejecting all callback operations and inline callbacks',
    async (auth) => {
      vi.mocked(lookup).mockClear();
      vi.mocked(postWebhook).mockClear();
      const agent = new Agent({ name: 'Public', description: 'Anonymous tasks', auth });
      agent.skill('count', { streaming: true }, async function* () {
        yield 'one';
      });
      const app = agent.buildApp();
      const taskId = await createTask(app, 'unused');
      expect((await rpc(app, 'unused', 'GetTask', { id: taskId })).body.result.id).toBe(taskId);
      for (const method of [
        'CreateTaskPushNotificationConfig',
        'GetTaskPushNotificationConfig',
        'ListTaskPushNotificationConfigs',
        'DeleteTaskPushNotificationConfig',
      ]) {
        const response = await rpc(app, 'unused', method, {
          taskId,
          id: 'callback',
          url: 'https://public.example/hook',
        });
        expect(response.body.error.message).toContain('Authentication is required');
      }
      const rest = await request(app).get(`/tasks/${taskId}/pushNotificationConfigs`).set('A2A-Version', '1.0');
      expect(rest.status).toBe(400);
      expect(rest.body.error.message).toContain('Authentication is required');
      for (const method of ['SendMessage', 'SendStreamingMessage']) {
        const response = await rpc(app, 'unused', method, {
          configuration: { taskPushNotificationConfig: { id: 'inline', url: 'https://public.example/hook' } },
          message: { messageId: 'inline', role: 'ROLE_USER', parts: [{ text: '{"skill":"count"}' }] },
        });
        expect(response.text).toContain('Authentication is required');
      }
      expect((await rpc(app, 'unused', 'ListTasks', {})).body.result.tasks).toHaveLength(1);
      expect(lookup).not.toHaveBeenCalled();
      expect(postWebhook).not.toHaveBeenCalled();
    },
  );

  it.each([
    { authenticate: async () => ({ authenticated: true, scopes: new Set<string>() }), getScheme: () => ({}) },
    {
      authenticate: async () => {
        throw new Error('sensitive verifier detail');
      },
      getScheme: () => ({}),
    },
  ])('fails closed for missing identities and verifier errors', async (auth) => {
    const agent = new Agent({ name: 'Secure', description: 'Test', auth });
    const response = await rpc(agent.buildApp(), 'token', 'ListTasks', {}).expect(401);
    expect(JSON.stringify(response.body)).not.toContain('sensitive');
  });
});
