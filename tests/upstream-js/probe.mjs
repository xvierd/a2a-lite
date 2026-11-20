import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { pathToFileURL } from 'node:url';
import { SendMessageRequest } from '@a2a-js/sdk';
import { ClientFactory, ClientFactoryOptions } from '@a2a-js/sdk/client';

const [liteEntry, sdkCommit] = process.argv.slice(2);
const { Agent, APIKeyAuth } = await import(pathToFileURL(liteEntry).href);
const token = randomUUID();
const agent = new Agent({
  name: 'JS SDK canary',
  description: 'Echoes a value supplied by the upstream client.',
  auth: new APIKeyAuth({ identities: { [token]: 'canary' } }),
  profile: 'authenticated',
});
agent.skill('echo', async ({ value }) => value);
const runtime = await agent.start({ host: '127.0.0.1', port: 0 });

try {
  for (const binding of ['JSONRPC', 'HTTP+JSON']) {
    const calls = [];
    const plugin = {
      name: 'test-client-hooks',
      beforeClientRequest(request) {
        calls.push(['before', request.method]);
        request.options.serviceParameters['X-API-Key'] = token;
      },
      aroundClientRequest(request, next) {
        calls.push(['around', request.method]);
        return next();
      },
      afterClientRequest(response) {
        calls.push(['after', response.method, response.isFinal]);
      },
    };
    const options = ClientFactoryOptions.createFrom(ClientFactoryOptions.default, {
      preferredTransports: [binding],
      clientConfig: { plugins: [plugin] },
    });
    const client = await new ClientFactory(options).createFromUrl(runtime.url);
    assert.equal(client.transport.protocolName, binding);
    assert.equal(client.endpoint, runtime.url);

    const value = randomUUID();
    const result = await client.sendMessage(SendMessageRequest.fromJSON({
      message: {
        role: 'ROLE_USER',
        messageId: randomUUID(),
        parts: [{ text: JSON.stringify({ skill: 'echo', params: { value } }) }],
      },
    }), { signal: AbortSignal.timeout(10_000) });
    assert.equal(result.parts[0].content.$case, 'text');
    assert.equal(result.parts[0].content.value, value);
    assert.deepEqual(calls, [
      ['before', 'SendMessage'],
      ['around', 'SendMessage'],
      ['after', 'SendMessage', true],
    ]);
    console.log(JSON.stringify({ sdkCommit, binding, endpoint: client.endpoint, hooks: calls }));
  }
} finally {
  await runtime.stop();
}
