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
