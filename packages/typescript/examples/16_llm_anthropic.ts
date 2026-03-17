/**
 * LLM integration with Anthropic.
 *
 * Uses the `anthropicSkill` factory to create skill handlers that call the
 * Anthropic messages API. No manual HTTP calls needed.
 *
 * Prerequisites:
 *   npm install @anthropic-ai/sdk
 *   export ANTHROPIC_API_KEY="sk-ant-..."
 *
 * Run: npx ts-node examples/16_llm_anthropic.ts
 */
import { Agent, anthropicSkill } from '../src';

const agent = new Agent({
  name: 'AnthropicAgent',
  description: 'An agent powered by Anthropic Claude models',
});

// Analysis skill — good for structured reasoning tasks
agent.skill('analyze', anthropicSkill({
  model: 'claude-opus-4-6',
  systemPrompt: 'You are an expert analyst. Break down the given topic into key insights, implications, and actionable recommendations.',
  maxTokens: 1024,
}));

// Code review skill — lower temperature for precise feedback
agent.skill('code_review', anthropicSkill({
  model: 'claude-opus-4-6',
  systemPrompt: 'You are a senior software engineer conducting a code review. Identify bugs, suggest improvements, and highlight good patterns. Be specific and constructive.',
  temperature: 0.3,
  maxTokens: 2048,
}));

// Streaming chat skill — yields tokens as they arrive
agent.skill('chat', { streaming: true }, anthropicSkill({
  model: 'claude-opus-4-6',
  systemPrompt: 'You are a helpful assistant.',
  streaming: true,
}));

agent.run({ port: 8787 });
