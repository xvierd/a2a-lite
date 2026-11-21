import request from 'supertest';
import { describe, expect, it } from 'vitest';
import { AgentCard } from '@a2a-js/sdk';
import { Agent, APIKeyAuth, BearerAuth, OAuth2Auth } from '../src/index.js';

describe('agent card protobuf wire format', () => {
  it.each([
    [new APIKeyAuth({ keys: ['secret'] }), 'apiKey', 'apiKeySecurityScheme'],
    [new BearerAuth({ validator: () => 'alice' }), 'bearer', 'httpAuthSecurityScheme'],
    [new OAuth2Auth({ issuer: 'https://issuer.example', audience: 'agent' }), 'oauth2', 'oauth2SecurityScheme'],
  ] as const)('serializes SDK security oneofs using the official wire serializer', async (auth, key, field) => {
    const agent = new Agent({ name: 'Card', description: 'Interop', auth });
    const response = await request(agent.buildApp()).get('/.well-known/agent-card.json').expect(200);
    expect(response.body.securitySchemes[key][field]).toBeDefined();
    expect(response.body.securitySchemes[key].scheme).toBeUndefined();
    expect(AgentCard.fromJSON(response.body).securitySchemes[key]).toEqual(agent.buildAgentCard().securitySchemes[key]);
  });
});

describe('free-text skill selection on the wire', () => {
  const send = async (agent: Agent, text: string) => {
    const response = await request(agent.buildApp())
      .post('/')
      .set('A2A-Version', '1.0')
      .send({
        jsonrpc: '2.0',
        id: 'test',
        method: 'SendMessage',
        params: { message: { messageId: 'm', role: 'ROLE_USER', parts: [{ text }] } },
      })
      .expect(200);
    return response.body.result.message.parts[0].text;
  };
  it('accepts free text for a single skill and reports the choices for an ambiguous message', async () => {
    const agent = new Agent({ name: 'Help', description: 'Help' });
    agent.skill('echo', async ({ message }) => message);
    expect(await send(agent, 'Hola')).toBe('Hola');
    agent.skill('other', async () => 'other');
    expect(JSON.parse(await send(agent, 'Hola'))).toMatchObject({
      type: 'SkillNotFoundError',
      available_skills: ['echo', 'other'],
    });
  });
  it('routes plain text to the configured skill and preserves explicit selection and errors', async () => {
    const agent = new Agent({ name: 'Help', description: 'Help', freeTextSkill: 'echo' });
    agent.skill('other', { tags: ['utility'] }, async () => 'selected');
    agent.skill('echo', async ({ message }) => message);
    expect(await send(agent, 'Hola')).toBe('Hola');
    expect(await send(agent, '{"skill":"other","params":{}}')).toBe('selected');
    expect(JSON.parse(await send(agent, '{"skill":"missing"}'))).toMatchObject({ type: 'SkillNotFoundError' });
    const response = await request(agent.buildApp()).get('/.well-known/agent-card.json').expect(200);
    expect(response.body.skills).toMatchObject([
      { id: 'other', tags: ['utility'] },
      { id: 'echo', tags: ['echo'], inputModes: ['application/json', 'text/plain'] },
    ]);
  });
  it('reports a misconfigured entry skill at startup', () => {
    const agent = new Agent({ name: 'Help', description: 'Help', freeTextSkill: 'missing' });
    expect(() => agent.buildApp()).toThrow("Unknown freeTextSkill 'missing'");
  });
});
