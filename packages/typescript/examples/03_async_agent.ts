/**
 * Agent demonstrating async operations.
 *
 * Run with: npx ts-node examples/03_async_agent.ts
 */
import { Agent } from '../src';

const agent = new Agent({
  name: 'AsyncDemo',
  description: 'Demonstrates async operations',
});

agent.skill('delay', { description: 'Wait for specified seconds' }, async ({ seconds = 1.0 }: { seconds?: number }) => {
  await new Promise(resolve => setTimeout(resolve, seconds * 1000));
  return { waited: seconds, message: `Waited for ${seconds} seconds` };
});

agent.skill('fetch_data', { description: 'Fetch data from a URL' }, async ({ url }: { url: string }) => {
  const response = await fetch(url);
  return { status: response.status, data: await response.json() };
});

agent.onStartup(() => console.log('Agent starting...'));
agent.onShutdown(() => console.log('Agent stopping...'));

agent.run({ port: 8787 });
