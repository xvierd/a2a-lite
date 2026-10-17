import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { Agent, APIKeyAuth } from '../src/index.js';

const origin = 'https://client.example';

function sendMessageParams() {
  return {
    message: {
      messageId: 'message-1',
      role: 'ROLE_USER',
      parts: [{ text: JSON.stringify({ skill: 'greet', params: { name: 'World' } }) }],
    },
  };
}

function createAgent(auth = false) {
  const agent = new Agent({
    name: 'HTTPBot',
    description: 'Tests the real SDK transport handlers',
    corsOrigins: [origin],
    auth: auth ? new APIKeyAuth({ keys: ['test-key'] }) : undefined,
  });
  agent.skill('greet', async ({ name }) => `Hello, ${name}!`);
  return agent;
}

describe('SDK HTTP integration', () => {
  it('serves the v1.0 agent card with browser access headers', async () => {
    const response = await request(createAgent().buildApp())
      .get('/.well-known/agent-card.json')
      .set('Origin', origin)
      .expect(200);

    expect(response.body.supportedInterfaces).toEqual(
      expect.arrayContaining([expect.objectContaining({ protocolBinding: 'JSONRPC', protocolVersion: '1.0' })]),
    );
    expect(response.body).not.toHaveProperty('protocolVersion');
    expect(response.headers['access-control-allow-origin']).toBe(origin);
    expect(response.headers.vary).toContain('Origin');
  });

  it('calls a skill through JSON-RPC with A2A version negotiation', async () => {
    const response = await request(createAgent().buildApp())
      .post('/')
      .set('A2A-Version', '1.0')
      .set('Origin', origin)
      .send({ jsonrpc: '2.0', id: 'rpc-1', method: 'SendMessage', params: sendMessageParams() })
      .expect(200);

    expect(response.body.result.message.parts).toEqual([{ text: 'Hello, World!' }]);
    expect(response.headers['access-control-allow-origin']).toBe(origin);
  });

  it.each(['application/json', 'application/a2a+json'])('accepts REST messages using %s', async (contentType) => {
    const response = await request(createAgent().buildApp())
      .post('/message:send')
      .set('A2A-Version', '1.0')
      .set('Content-Type', contentType)
      .send(JSON.stringify(sendMessageParams()))
      .expect(200);

    expect(response.headers['content-type']).toContain('application/a2a+json');
    expect(response.body.message.parts).toEqual([{ text: 'Hello, World!' }]);
  });

  it('returns protocol errors in JSON-RPC envelopes with HTTP 200', async () => {
    const response = await request(createAgent().buildApp())
      .post('/')
      .set('A2A-Version', '1.0')
      .send({ jsonrpc: '2.0', id: 'rpc-2', method: 'GetTask', params: { id: 'missing-task' } })
      .expect(200);

    expect(response.body).toMatchObject({ jsonrpc: '2.0', id: 'rpc-2', error: { code: -32001 } });
  });

  it('allows authenticated browser preflights to request A2A headers', async () => {
    const response = await request(createAgent(true).buildApp())
      .options('/')
      .set('Origin', origin)
      .set('Access-Control-Request-Method', 'POST')
      .set('Access-Control-Request-Headers', 'content-type,a2a-version,a2a-extensions,x-api-key')
      .expect(204);

    expect(response.headers['access-control-allow-origin']).toBe(origin);
    expect(response.headers['access-control-allow-headers']).toContain('A2A-Version');
    expect(response.headers['access-control-allow-headers']).toContain('A2A-Extensions');
    expect(response.headers['access-control-allow-methods']).toContain('DELETE');
  });

  it('includes CORS headers on authentication errors without bypassing authentication', async () => {
    const response = await request(createAgent(true).buildApp())
      .post('/')
      .set('Origin', origin)
      .set('A2A-Version', '1.0')
      .send({ jsonrpc: '2.0', id: 'rpc-3', method: 'SendMessage', params: sendMessageParams() })
      .expect(401);

    expect(response.headers['access-control-allow-origin']).toBe(origin);
    expect(response.body.error).toBeDefined();
  });

  it('does not grant browser access to an unlisted origin', async () => {
    const response = await request(createAgent().buildApp())
      .get('/.well-known/agent-card.json')
      .set('Origin', 'https://unlisted.example')
      .expect(200);

    expect(response.headers['access-control-allow-origin']).toBeUndefined();
  });
});
