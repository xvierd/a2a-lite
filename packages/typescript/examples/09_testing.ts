/**
 * Testing your agents.
 *
 * Run: npx ts-node examples/09_testing.ts
 */
import { Agent, AgentTestClient } from '../src';

const agent = new Agent({ name: 'Calculator', description: 'Math operations' });

agent.skill('add', async ({ a, b }: { a: number; b: number }) => a + b);
agent.skill('multiply', async ({ a, b }: { a: number; b: number }) => a * b);
agent.skill('divide', async ({ a, b }: { a: number; b: number }) => {
  if (b === 0) return { error: 'Cannot divide by zero' };
  return { result: a / b };
});

async function runTests() {
  console.log('Running tests...\n');
  const client = new AgentTestClient(agent);

  // Test add
  const sum = await client.call('add', { a: 2, b: 3 });
  console.assert(sum.data === 5, 'Expected 5');
  console.log('test_add passed');

  // Test multiply
  const product = await client.call('multiply', { a: 4, b: 5 });
  console.assert(product.data === 20, 'Expected 20');
  console.log('test_multiply passed');

  // Test divide
  const quotient = await client.call('divide', { a: 10, b: 2 });
  console.assert((quotient.data as any).result === 5, 'Expected 5');
  console.log('test_divide passed');

  // Test divide by zero
  const error = await client.call('divide', { a: 10, b: 0 });
  console.assert('error' in (error.data as any), 'Expected error');
  console.log('test_divide_by_zero passed');

  // Test list skills
  const skills = client.listSkills();
  console.assert(skills.includes('add'), 'Expected add skill');
  console.assert(skills.includes('multiply'), 'Expected multiply skill');
  console.assert(skills.includes('divide'), 'Expected divide skill');
  console.log('test_list_skills passed');

  // Test get agent card
  const card = client.getAgentCard();
  console.assert(card.name === 'Calculator', 'Expected Calculator');
  console.assert(card.skills?.length === 3, 'Expected 3 skills');
  console.log('test_get_agent_card passed');

  console.log('\nAll tests passed!');
}

runTests();
