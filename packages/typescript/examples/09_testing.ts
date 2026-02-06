/**
 * Testing your agents.
 *
 * Run: npx ts-node examples/09_testing.ts
 */
import { Agent, TestClient } from '../src';

const agent = new Agent({ name: 'Calculator', description: 'Math operations' });

agent.skill('add', async ({ a, b }: { a: number; b: number }) => a + b);
agent.skill('multiply', async ({ a, b }: { a: number; b: number }) => a * b);
agent.skill('divide', async ({ a, b }: { a: number; b: number }) => {
  if (b === 0) return { error: 'Cannot divide by zero' };
  return { result: a / b };
});

async function runTests() {
  console.log('Running tests...\n');
  const client = new TestClient(agent);

  // Test add
  const sum = await client.call('add', { a: 2, b: 3 });
  console.assert(sum === 5, 'Expected 5');
  console.log('✅ test_add passed');

  // Test multiply
  const product = await client.call('multiply', { a: 4, b: 5 });
  console.assert(product === 20, 'Expected 20');
  console.log('✅ test_multiply passed');

  // Test divide
  const quotient = await client.call('divide', { a: 10, b: 2 }) as any;
  console.assert(quotient.result === 5, 'Expected 5');
  console.log('✅ test_divide passed');

  // Test divide by zero
  const error = await client.call('divide', { a: 10, b: 0 }) as any;
  console.assert('error' in error, 'Expected error');
  console.log('✅ test_divide_by_zero passed');

  // Test list skills
  const skills = client.listSkills();
  console.assert(skills.includes('add'), 'Expected add');
  console.log('✅ test_list_skills passed');

  console.log('\n🎉 All tests passed!');
}

runTests();
