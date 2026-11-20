import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { Agent, callRemoteSkill, callRemoteSkillWithHandle, streamRemoteSkill } from 'a2a-lite';

const require = createRequire(import.meta.url);
assert.equal(typeof require('a2a-lite').Agent, 'function');
const agent = new Agent({ name: 'Release', description: 'Published package smoke' });
agent.skill('echo', { tags: ['release'] }, async ({ text }) => text);
agent.skill('tracked', { tags: ['release'], task: true, taskContext: true }, async ({ task }) => task.taskId);
agent.skill('stream', { tags: ['release'], streaming: true }, async function* () {
  yield 'first';
  yield 'second';
});

const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
try {
  assert.equal(await callRemoteSkill(runtime.url, 'echo', { text: 'hello' }), 'hello');
  const handle = await callRemoteSkillWithHandle(runtime.url, 'tracked', {});
  assert.ok(handle.taskId);
  assert.equal(handle.result, handle.taskId);
  const task = await handle.getStatus();
  assert.equal(task.id, handle.taskId);
  assert.equal(task.status.state, 'TASK_STATE_COMPLETED');
  const chunks = [];
  for await (const part of streamRemoteSkill(runtime.url, 'stream', {})) chunks.push(part);
  assert.deepEqual(chunks, ['first', 'second']);
} finally {
  await runtime.stop();
}
