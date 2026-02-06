/**
 * Simplest possible A2A Lite agent.
 *
 * Run with: npx ts-node examples/01_hello_world.ts
 */
import { Agent } from '../src';

const agent = new Agent({
  name: 'HelloWorld',
  description: 'A simple greeting agent',
});

agent.skill('greet', { description: 'Greet someone by name' }, async ({ name = 'World' }) => {
  return `Hello, ${name}!`;
});

agent.run({ port: 8787 });
