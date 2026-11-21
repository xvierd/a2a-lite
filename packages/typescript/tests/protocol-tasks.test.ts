import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { Agent, AgentNetwork, callRemoteSkillWithHandle, TaskContext, type AgentRuntime } from '../src/index.js';

const message = (skill: string, configuration: Record<string, unknown> = {}) => ({
  jsonrpc: '2.0',
  id: '1',
  method: 'SendMessage',
  params: {
    configuration,
    message: { messageId: 'm', role: 'ROLE_USER', parts: [{ text: JSON.stringify({ skill }) }] },
  },
});
const rpc = (runtime: AgentRuntime, method: string, params: Record<string, unknown>) =>
  request(runtime.url).post('/').set('A2A-Version', '1.0').send({ jsonrpc: '2.0', id: '2', method, params });

describe('real protocol task lifecycle', () => {
  it('unifies TaskContext ID, result artifact, progress, GetTask and Task errors', async () => {
    const agent = new Agent({ name: 'Tasks', description: 'Protocol tasks' });
    let id = '';
    agent.skill('identity', { task: true, taskContext: true }, async ({ task }) => {
      const context = task as TaskContext;
      id = context.taskId;
      await context.update('working', 'half', 0.5);
      return id;
    });
    agent.skill('fail', { task: true }, async () => {
      throw new Error('Expected failure');
    });
    const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
    try {
      const response = await request(runtime.url).post('/').set('A2A-Version', '1.0').send(message('identity'));
      expect(response.body.result.task.id).toBe(id);
      expect(response.body.result.task.artifacts[0].parts[0].text).toBe(id);
      expect((await rpc(runtime, 'GetTask', { id })).body.result.status.state).toBe('TASK_STATE_COMPLETED');
      const failed = await request(runtime.url).post('/').set('A2A-Version', '1.0').send(message('fail'));
      expect(failed.body.result.task.status.state).toBe('TASK_STATE_FAILED');
    } finally {
      await runtime.stop();
    }
  });
  it('resubscribes to a live task and follows two ListTasks pages with the public client', async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const agent = new Agent({ name: 'Work', description: 'Task streaming' });
    agent.skill('work', { task: true }, async () => {
      await gate;
      return 'done';
    });
    const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
    const network = new AgentNetwork({ worker: runtime.url });
    try {
      expect((await network.discover('worker')).supportsStreaming).toBe(true);
      const first = await callRemoteSkillWithHandle(runtime.url, 'work', {}, 4000, { returnImmediately: true });
      const updates = first.streamEvents(4000);
      const snapshot = await updates.next();
      expect(snapshot.value).toMatchObject({ $case: 'task', value: { id: first.taskId } });
      release();
      const received = [];
      for await (const update of updates) received.push(update);
      expect(received.map((e) => e.$case)).toContain('artifactUpdate');
      expect(received.at(-1)?.raw).toMatchObject({ statusUpdate: { status: { state: 'TASK_STATE_COMPLETED' } } });

      const second = await callRemoteSkillWithHandle(runtime.url, 'work', {});
      const page = await network.listTasks('worker', { pageSize: 1, includeArtifacts: true });
      expect(page.nextPageToken).toBeTruthy();
      const next = await network.listTasks('worker', {
        pageSize: 1,
        includeArtifacts: true,
        pageToken: page.nextPageToken,
      });
      expect(next.nextPageToken).toBe('');
      expect([...page.tasks, ...next.tasks].map((t) => t.id).sort()).toEqual([first.taskId, second.taskId].sort());
      expect(page.tasks[0].artifacts[0].parts[0].content).toEqual({ $case: 'text', value: 'done' });
    } finally {
      release();
      await runtime.stop();
    }
  });
  it('cancels the cooperative running skill and suppresses later completion', async () => {
    const agent = new Agent({ name: 'Cancel', description: 'Cooperative cancel' });
    let observed = false;
    agent.skill('wait', { task: true, taskContext: true }, async ({ task }) => {
      const context = task as TaskContext;
      await new Promise<void>((resolve) =>
        context.signal.addEventListener(
          'abort',
          () => {
            observed = true;
            resolve();
          },
          { once: true },
        ),
      );
      return 'late completion';
    });
    const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
    try {
      const response = await request(runtime.url)
        .post('/')
        .set('A2A-Version', '1.0')
        .send(message('wait', { returnImmediately: true }));
      const id = response.body.result.task.id;
      expect((await rpc(runtime, 'CancelTask', { id })).body.result.status.state).toBe('TASK_STATE_CANCELED');
      expect(observed).toBe(true);
      expect((await rpc(runtime, 'GetTask', { id })).body.result.status.state).toBe('TASK_STATE_CANCELED');
    } finally {
      await runtime.stop();
    }
  });
  it('finishes timed-out task state and closes the runtime without process signals', async () => {
    const agent = new Agent({ name: 'Deadline', description: 'Bounded task', limits: { executionTimeoutMs: 20 } });
    agent.skill('wait', { task: true }, async () => new Promise(() => {}));
    const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
    const response = await request(runtime.url).post('/').set('A2A-Version', '1.0').send(message('wait'));
    expect(response.body.result.task.status.state).toBe('TASK_STATE_FAILED');
    expect(response.body.result.task.status.message.parts[0].text).toContain('deadline');
    await Promise.all([runtime.stop(), runtime.stop()]);
    await runtime.closed;
    expect(runtime.stats.closing).toBe(true);
  });
});
