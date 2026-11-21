import assert from 'node:assert/strict';
import { AgentNetwork, RemoteAgentError } from '../../packages/typescript/src/index.ts';

const url = process.argv[2];
const network = new AgentNetwork();
const tenants = ['blue', 'green'];
for (const tenant of tenants) {
  network.add(tenant, url + '/' + tenant);
  assert.equal((await network.discover(tenant)).url, url + '/rpc');
}
assert.deepEqual(await Promise.all(tenants.map((name) => network.call(name, 'tenant'))), tenants);

const chunks: string[] = [];
await assert.rejects(
  async () => {
    for await (const chunk of network.stream('blue', 'streamError')) chunks.push(chunk);
  },
  (err: unknown) => err instanceof RemoteAgentError && err.code === -32602,
);
assert.deepEqual(chunks, ['before-error:blue']);
console.log('A2A_LITE_STREAM_ERROR_VERIFIED');
