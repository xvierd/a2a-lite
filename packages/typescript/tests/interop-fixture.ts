import assert from 'node:assert/strict';
import {
  Agent,
  APIKeyAuth,
  TaskContext,
  TaskHandle,
  callRemoteSkill,
  callRemoteSkillWithHandle,
  createPostgresPersistence,
  streamRemoteSkill,
} from '../src/index.js';

const args = process.argv.slice(2);
const option = (name: string) => args[args.indexOf(name) + 1];
if (args[0] === 'server') {
  const agent = new Agent({
    name: 'TypeScriptInterop',
    description: 'Cross-language contract fixture',
    profile: process.env.A2ALITE_INTEROP_POSTGRES_DSN ? 'durable' : 'authenticated',
    persistence: process.env.A2ALITE_INTEROP_POSTGRES_DSN
      ? await createPostgresPersistence({
          connectionString: process.env.A2ALITE_INTEROP_POSTGRES_DSN,
          encryptionKey: Buffer.alloc(32, 7).toString('base64'),
          delivery: process.env.A2ALITE_INTEROP_DISTRIBUTED ? { autoStart: false } : undefined,
          execution: process.env.A2ALITE_INTEROP_DISTRIBUTED ? {} : undefined,
        })
      : undefined,
    auth: new APIKeyAuth({
      identities: { 'interop-secret': 'alice', 'interop-rotated': 'alice', 'interop-other': 'bob' },
    }),
  });
  agent.skill('delay', async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
    return 'ok';
  });
  agent.skill('greet', async ({ text }) => text);
  agent.skill('taskProbe', { task: true, taskContext: true }, async ({ task }) => (task as TaskContext).taskId);
  agent.skill('pause', { task: true, taskContext: true }, async ({ task, resume }) => {
    if (resume === true) return 'resumed';
    await (task as TaskContext).update('input-required', 'Continue with resume=true');
    return undefined;
  });
  agent.skill('hold', { streaming: true, taskContext: true }, async function* ({ task }) {
    const context = task as TaskContext;
    for (let index = 0; index < 100; index++) {
      await new Promise((resolve) => setTimeout(resolve, 50));
      context.signal.throwIfAborted();
      yield String(index);
    }
  });
  agent.skill('stream', { streaming: true }, async function* () {
    yield 'one';
    yield 'two';
    yield 'three';
  });
  agent.skill('fail', { task: true }, async () => {
    throw new Error('Expected fixture failure');
  });
  const runtime = await agent.start({ host: '127.0.0.1', port: Number(option('--port')) });
  for (const signal of ['SIGTERM', 'SIGINT'] as const)
    process.once(signal, () => {
      void runtime.stop();
    });
  console.log('A2A_LITE_READY ' + JSON.stringify({ url: runtime.url }));
} else if (args[0] === 'client') {
  const url = option('--url');
  const options = { headers: { 'X-API-Key': 'interop-secret' } };
  assert.equal(await callRemoteSkill(url, 'greet', { text: 'hello' }, 10000, options), 'hello');
  const handle = (await callRemoteSkillWithHandle(url, 'taskProbe', {}, 10000, options)) as TaskHandle;
  assert.equal(handle.result, handle.taskId);
  assert.equal((await handle.get()).id, handle.taskId);
  const chunks: string[] = [];
  for await (const chunk of streamRemoteSkill(url, 'stream', {}, 10000, options)) chunks.push(chunk);
  assert.deepEqual(chunks.filter(Boolean), ['one', 'two', 'three']);
  console.log('A2A_LITE_RESULT ' + JSON.stringify({ message: true, task: true, taskRead: true, stream: true }));
} else throw new Error('Expected server --port N or client --url URL');
