import { describe, expect, it, vi } from 'vitest';
import request from 'supertest';
import { Agent, APIKeyAuth, BearerAuth, CompositeAuth, NoAuth } from '../src/index.js';
const body = {
  jsonrpc: '2.0',
  id: '1',
  method: 'SendMessage',
  params: { message: { messageId: 'm', role: 'ROLE_USER', parts: [{ text: '{"skill":"wait"}' }] } },
};

describe('managed runtime limits and profiles', () => {
  it('owns one listener, closes idempotently, and cleans all hooks after a failed hook', async () => {
    const before = process.listenerCount('SIGTERM');
    const agent = new Agent({ name: 'Lifecycle', description: 'Managed' });
    const last = vi.fn();
    agent.onShutdown(() => {
      throw new Error('shutdown failure');
    });
    agent.onShutdown(last);
    const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
    expect(process.listenerCount('SIGTERM')).toBe(before);
    await expect(agent.start()).rejects.toThrow('already started');
    await request(runtime.url).get('/health/ready').expect(200, { ready: true });
    await expect(runtime.stop()).rejects.toThrow('shutdown failure');
    await runtime.closed;
    expect(last).toHaveBeenCalledOnce();
  });
  it('rejects incompatible profiles and anonymous fallbacks at startup or authentication', async () => {
    for (const auth of [undefined, new CompositeAuth([new APIKeyAuth({ keys: ['secret'] }), new NoAuth()])]) {
      expect(() =>
        new Agent({ name: 'No', description: 'Profile', profile: 'authenticated', auth }).buildApp(),
      ).toThrow('authentication provider');
    }
    expect(() =>
      new Agent({
        name: 'No',
        description: 'Profile',
        profile: 'durable',
        auth: new BearerAuth({ validator: () => 'alice' }),
      }).buildApp(),
    ).toThrow('persistent protocol stores');
    const agent = new Agent({
      name: 'Custom',
      description: 'Fails closed',
      profile: 'authenticated',
      auth: {
        getScheme: () => ({ type: 'http' }),
        authenticate: async () => ({ authenticated: true, anonymous: true, userId: 'anonymous' }),
      },
    });
    await request(agent.buildApp()).post('/').send(body).expect(401);
  });
  it('bounds admission and body size while keeping health independent', async () => {
    let release!: () => void;
    const agent = new Agent({
      name: 'Limits',
      description: 'Bounded',
      limits: { maxConcurrentRequests: 1, bodyLimitBytes: 512 },
    });
    agent.skill(
      'wait',
      async () =>
        new Promise((resolve) => {
          release = () => resolve('done');
        }),
    );
    const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
    try {
      const first = request(runtime.url)
        .post('/')
        .set('A2A-Version', '1.0')
        .send(body)
        .then((response) => response);
      await vi.waitFor(() => expect(release).toBeTypeOf('function'));
      await request(runtime.url).post('/').set('A2A-Version', '1.0').send(body).expect(503);
      await request(runtime.url).get('/health/live').expect(200);
      release();
      await first;
      await request(runtime.url)
        .post('/')
        .set('A2A-Version', '1.0')
        .send({ padding: 'x'.repeat(1024) })
        .expect(413);
      expect(runtime.stats.activeRequests).toBe(0);
      expect(runtime.stats.rejectedRequests).toBe(1);
    } finally {
      release?.();
      await runtime.stop();
    }
  });
  it('rolls back startup hooks on bind errors and startup failures', async () => {
    const first = new Agent({ name: 'First', description: 'Bind' });
    const running = await first.start({ host: '127.0.0.1', port: 0 });
    const shutdown = vi.fn();
    const second = new Agent({ name: 'Second', description: 'Bind' }).onShutdown(shutdown);
    await expect(second.start({ host: '127.0.0.1', port: Number(new URL(running.url).port) })).rejects.toThrow();
    expect(shutdown).toHaveBeenCalledOnce();
    await running.stop();
  });
  it('bounds both accumulated stream events and non-streaming result bytes', async () => {
    const agent = new Agent({
      name: 'Output',
      description: 'Finite output',
      limits: { maxEventsPerExecution: 4, maxOutputBytes: 256 },
    });
    agent.skill('many', { streaming: true }, async function* () {
      for (let i = 0; i < 100; i++) yield 'chunk';
    });
    agent.skill('large', { task: true }, async () => 'x'.repeat(1024));
    const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
    try {
      for (const skill of ['many', 'large']) {
        const payload = structuredClone(body);
        payload.params.message.parts[0].text = JSON.stringify({ skill });
        const response = await request(runtime.url).post('/').set('A2A-Version', '1.0').send(payload);
        expect(response.body.result.task.status.state).toBe('TASK_STATE_FAILED');
        expect(response.body.result.task.status.message.parts[0].text).toContain('output limit');
      }
    } finally {
      await runtime.stop();
    }
  });
});
