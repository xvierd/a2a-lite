/**
 * Agent that uses an LLM for intelligent responses.
 *
 * Run: export OPENAI_API_KEY=your-key && npx ts-node examples/05_with_llm.ts
 */
import { Agent } from '../src';

let openai: any = null;
try {
  const OpenAI = require('openai').default;
  if (process.env.OPENAI_API_KEY) {
    openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  }
} catch {}

async function chat(message: string): Promise<Record<string, unknown>> {
  if (!openai) return { error: 'Set OPENAI_API_KEY' };
  try {
    const response = await openai.chat.completions.create({
      model: process.env.OPENAI_MODEL || 'gpt-4o-mini',
      messages: [{ role: 'user', content: message }],
      max_tokens: 500,
    });
    return { response: response.choices[0].message.content };
  } catch (e: any) { return { error: e.message }; }
}

const agent = new Agent({ name: 'SmartAssistant', description: 'AI-powered assistant' });

agent.skill('chat', { description: 'Chat with AI' }, async ({ message }: { message: string }) => chat(message));
agent.skill('summarize', { description: 'Summarize text' }, async ({ text }: { text: string }) =>
  chat(`Summarize in 100 words: ${text}`));

if (!openai) console.log('WARNING: Set OPENAI_API_KEY for LLM features');
agent.run({ port: 8787 });
