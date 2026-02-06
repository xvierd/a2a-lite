/**
 * Calculator agent with multiple skills.
 *
 * Run with: npx ts-node examples/02_calculator.ts
 */
import { Agent } from '../src';

const agent = new Agent({
  name: 'Calculator',
  description: 'Performs mathematical operations',
  version: '1.0.0',
});

agent.skill('add', { description: 'Add two numbers' }, async ({ a, b }: { a: number; b: number }) => a + b);
agent.skill('subtract', { description: 'Subtract b from a' }, async ({ a, b }: { a: number; b: number }) => a - b);
agent.skill('multiply', { description: 'Multiply two numbers' }, async ({ a, b }: { a: number; b: number }) => a * b);
agent.skill('divide', { description: 'Divide a by b' }, async ({ a, b }: { a: number; b: number }) => {
  if (b === 0) return { error: 'Cannot divide by zero' };
  return { result: a / b };
});

agent.onError(async (error) => ({
  error: error.message,
  type: error.name,
  hint: 'Check your input parameters',
}));

agent.run({ port: 8787 });
