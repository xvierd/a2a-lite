/**
 * Authentication (optional).
 *
 * Run: npx ts-node examples/14_with_auth.ts
 * Test: curl -H "X-API-Key: secret-key" http://localhost:8787/
 */
import { Agent, APIKeyAuth } from '../src';

const agent = new Agent({
  name: 'SecureBot',
  description: 'Bot with authentication',
  auth: new APIKeyAuth({ keys: ['secret-key', 'another-key'], header: 'X-API-Key' }),
});

agent.skill('public_info', { description: 'Available to authenticated users' }, async () => ({ message: "You're authenticated!" }));

agent.skill('get_secrets', { description: 'Get secret data' }, async () => ({
  secrets: ['secret1', 'secret2'],
  message: 'Authenticated only',
}));

console.log("Test with: curl -H 'X-API-Key: secret-key' http://localhost:8787/");
agent.run({ port: 8787 });
