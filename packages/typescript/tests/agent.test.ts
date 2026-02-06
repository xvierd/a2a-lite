import { describe, it, expect } from 'vitest';
import { Agent, AgentTestClient } from '../src/index.js';

describe('Agent', () => {
  it('should create an agent with name and description', () => {
    const agent = new Agent({ name: 'TestBot', description: 'A test bot' });
    expect(agent.name).toBe('TestBot');
    expect(agent.description).toBe('A test bot');
  });

  it('should register a skill', () => {
    const agent = new Agent({ name: 'Bot', description: 'Test' });

    agent.skill('greet', async ({ name }: { name: string }) => {
      return `Hello, ${name}!`;
    });

    const card = agent.buildAgentCard();
    expect(card.skills).toHaveLength(1);
    expect(card.skills[0].name).toBe('greet');
  });

  it('should build agent card', () => {
    const agent = new Agent({
      name: 'TestBot',
      description: 'A test bot',
      version: '2.0.0',
    });

    agent.skill('greet', async () => 'Hello');
    agent.skill('farewell', async () => 'Goodbye');

    const card = agent.buildAgentCard('localhost', 9000);

    expect(card.name).toBe('TestBot');
    expect(card.version).toBe('2.0.0');
    expect(card.url).toBe('http://localhost:9000/a2a/jsonrpc');
    expect(card.skills).toHaveLength(2);
  });
});

describe('AgentTestClient', () => {
  it('should call a skill', async () => {
    const agent = new Agent({ name: 'Bot', description: 'Test' });

    agent.skill('greet', async ({ name }: { name: string }) => {
      return `Hello, ${name}!`;
    });

    const client = new AgentTestClient(agent);
    const result = await client.call('greet', { name: 'World' });

    expect(result.data).toBe('Hello, World!');
  });

  it('should return dict results', async () => {
    const agent = new Agent({ name: 'Bot', description: 'Test' });

    agent.skill('info', async ({ id }: { id: number }) => {
      return { id, status: 'active' };
    });

    const client = new AgentTestClient(agent);
    const result = await client.call('info', { id: 42 });

    expect(result.data).toEqual({ id: 42, status: 'active' });
  });

  it('should list skills', () => {
    const agent = new Agent({ name: 'Bot', description: 'Test' });

    agent.skill('skill1', async () => 'one');
    agent.skill('skill2', async () => 'two');

    const client = new AgentTestClient(agent);
    const skills = client.listSkills();

    expect(skills).toContain('skill1');
    expect(skills).toContain('skill2');
  });

  it('should stream results', async () => {
    const agent = new Agent({ name: 'Bot', description: 'Test' });

    agent.skill('count', { streaming: true }, async function* ({ n }: { n: number }) {
      for (let i = 1; i <= n; i++) {
        yield `Count: ${i}`;
      }
    });

    const client = new AgentTestClient(agent);
    const results = await client.stream('count', { n: 3 });

    expect(results).toEqual(['Count: 1', 'Count: 2', 'Count: 3']);
  });
});
