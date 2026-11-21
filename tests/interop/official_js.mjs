// Exercise the public JavaScript ClientFactory on one advertised binding.
import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { parseArgs } from 'node:util';

const require = createRequire(new URL('../../packages/typescript/package.json', import.meta.url));
const { ClientFactory, JsonRpcTransportFactory, RestTransportFactory } = require('@a2a-js/sdk/client');
const { TaskNotFoundError } = require('@a2a-js/sdk/errors');
const { Role, SendMessageRequest, TaskState } = require('@a2a-js/sdk');
const { version } = require(resolve(dirname(require.resolve('@a2a-js/sdk')), '../package.json'));
const {
  values: { url, binding },
} = parseArgs({
  options: { url: { type: 'string' }, binding: { type: 'string' } },
});
assert.ok(url, 'Expected --url URL');
assert.ok(['JSONRPC', 'HTTP+JSON'].includes(binding), 'Expected --binding JSONRPC or HTTP+JSON');

const transport = binding === 'JSONRPC' ? new JsonRpcTransportFactory() : new RestTransportFactory();
const client = await new ClientFactory({ transports: [transport] }).createFromUrl(url);
const options = { serviceParameters: { 'X-API-Key': 'interop-secret' }, signal: AbortSignal.timeout(20000) };

function message(skill, params = {}) {
  return SendMessageRequest.fromJSON({
    message: { messageId: randomUUID(), role: 'ROLE_USER', parts: [{ text: JSON.stringify({ skill, params }) }] },
  });
}

function texts(parts = []) {
  return parts.filter((part) => part.content?.$case === 'text').map((part) => part.content.value);
}

const greeting = await client.sendMessage(message('greet', { text: 'hello' }), options);
assert.ok(greeting.messageId, 'greet did not return a Message');
assert.equal(greeting.role, Role.ROLE_AGENT);
assert.deepEqual(texts(greeting.parts), ['hello']);

const task = await client.sendMessage(message('taskProbe'), options);
assert.ok(task.id, 'taskProbe did not return a Task');
assert.equal(task.status?.state, TaskState.TASK_STATE_COMPLETED);
const result = [...texts(task.status.message?.parts), ...task.artifacts.flatMap((artifact) => texts(artifact.parts))];
assert.ok(result.includes(task.id), 'taskProbe did not receive the returned Task ID');
const read = await client.getTask({ id: task.id }, options);
assert.equal(read.id, task.id);
assert.equal(read.status?.state, TaskState.TASK_STATE_COMPLETED);

await assert.rejects(client.getTask({ id: randomUUID() }, options), TaskNotFoundError);

async function checkStream(skill, terminal) {
  let taskId;
  let ended = false;
  const chunks = [];
  for await (const { payload } of client.sendMessageStream(message(skill), options)) {
    assert.ok(!ended, `${skill}: event after terminal status`);
    if (!taskId) {
      assert.equal(payload?.$case, 'task', `${skill}: missing initial Task`);
      taskId = payload.value.id;
      assert.ok(taskId);
      continue;
    }
    assert.equal(payload.value.taskId, taskId, `${skill}: event for another Task`);
    if (payload.$case === 'artifactUpdate') {
      chunks.push(...texts(payload.value.artifact.parts));
      continue;
    }
    assert.equal(payload.$case, 'statusUpdate');
    const { state, message } = payload.value.status;
    ended = state === terminal;
    assert.ok(
      ended || state === TaskState.TASK_STATE_SUBMITTED || state === TaskState.TASK_STATE_WORKING,
      `${skill}: unexpected state ${state}`,
    );
    chunks.push(...texts(message?.parts));
  }
  assert.ok(ended, `${skill}: stream closed before the expected terminal status`);
  if (skill === 'stream') assert.deepEqual(chunks, ['one', 'two', 'three']);
}

await checkStream('stream', TaskState.TASK_STATE_COMPLETED);
await checkStream('fail', TaskState.TASK_STATE_FAILED);
console.log(
  'A2A_LITE_OFFICIAL ' +
    JSON.stringify({
      sdk: '@a2a-js/sdk',
      sdkVersion: version,
      binding,
      message: true,
      task: true,
      taskRead: true,
      taskNotFound: true,
      stream: true,
      failure: true,
    }),
);
