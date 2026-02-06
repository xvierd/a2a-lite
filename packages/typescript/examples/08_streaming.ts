/**
 * Streaming responses (like ChatGPT).
 *
 * Run: npx ts-node examples/08_streaming.ts
 */
import { Agent } from '../src';

const agent = new Agent({ name: 'StreamingDemo', description: 'Shows streaming' });

agent.skill('count', { description: 'Count from 1 to n', streaming: true }, async function* ({ n = 5, delay = 0.5 }: { n?: number; delay?: number }) {
  for (let i = 1; i <= n; i++) {
    yield 'Count: ' + i + '\n';
    await new Promise(resolve => setTimeout(resolve, delay * 1000));
  }
  yield 'Done!';
});

agent.skill('typewriter', { description: 'Type message slowly', streaming: true }, async function* ({ message, delay = 0.05 }: { message: string; delay?: number }) {
  for (const char of message) {
    yield char;
    await new Promise(resolve => setTimeout(resolve, delay * 1000));
  }
});

agent.skill('fake_llm', { description: 'Simulate LLM streaming', streaming: true }, async function* ({ prompt }: { prompt: string }) {
  const words = ('You asked: ' + prompt + '. Here is my response.').split(' ');
  for (const word of words) {
    yield word + ' ';
    await new Promise(resolve => setTimeout(resolve, 100));
  }
});

agent.run({ port: 8787 });
