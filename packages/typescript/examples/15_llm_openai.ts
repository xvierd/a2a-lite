/**
 * LLM integration with OpenAI.
 *
 * Uses the `openaiSkill` factory to create skill handlers that call the
 * OpenAI chat completions API. No manual HTTP calls needed.
 *
 * Prerequisites:
 *   npm install openai
 *   export OPENAI_API_KEY="sk-..."
 *
 * Run: npx ts-node examples/15_llm_openai.ts
 */
import { Agent, openaiSkill } from '../src';

const agent = new Agent({
  name: 'OpenAIAgent',
  description: 'An agent powered by OpenAI models',
});

// Basic chat skill (non-streaming)
agent.skill('chat', openaiSkill({
  model: 'gpt-4o-mini',
  systemPrompt: 'You are a helpful assistant.',
}));

// Summarization skill with lower temperature for more focused output
agent.skill('summarize', openaiSkill({
  model: 'gpt-4o-mini',
  systemPrompt: 'You are an expert summarizer. Provide concise, clear summaries of the given text.',
  temperature: 0.3,
  maxTokens: 512,
}));

// Translation skill
agent.skill('translate', openaiSkill({
  model: 'gpt-4o-mini',
  systemPrompt: 'You are a professional translator. Translate the given text to the target language specified in the message. If no target language is specified, translate to English.',
  temperature: 0.2,
}));

// Streaming chat skill — yields tokens as they arrive
agent.skill('stream_chat', { streaming: true }, openaiSkill({
  model: 'gpt-4o-mini',
  systemPrompt: 'You are a helpful assistant.',
  streaming: true,
}));

agent.run({ port: 8787 });
