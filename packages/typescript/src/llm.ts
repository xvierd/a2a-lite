/**
 * LLM integration for A2A Lite TypeScript.
 *
 * Provides higher-order functions that wrap skill handlers to call LLM APIs.
 * Uses dynamic import() so LLM SDKs are optional peer dependencies.
 *
 * Usage:
 *   import { openaiSkill, anthropicSkill } from 'a2a-lite';
 *
 *   agent.skill("chat", openaiSkill({ model: "gpt-4o-mini" }));
 *
 *   agent.skill("analyze", anthropicSkill({ model: "claude-sonnet-4-6" }));
 */

export interface OpenAISkillConfig {
  model?: string;
  systemPrompt?: string;
  temperature?: number;
  maxTokens?: number;
  streaming?: boolean;
}

export interface AnthropicSkillConfig {
  model?: string;
  systemPrompt?: string;
  temperature?: number;
  maxTokens?: number;
  streaming?: boolean;
}

type SkillHandler = (params: Record<string, unknown>) => Promise<unknown> | AsyncGenerator<unknown>;

/**
 * Returns a SkillHandler that calls the OpenAI chat completions API.
 *
 * Requires: npm install openai
 *
 * @example
 *   agent.skill("chat", openaiSkill({ model: "gpt-4o-mini", systemPrompt: "You are helpful." }));
 *   // or streaming:
 *   agent.skill("chat", { streaming: true }, openaiSkill({ model: "gpt-4o-mini", streaming: true }));
 */
export function openaiSkill(config: OpenAISkillConfig = {}): SkillHandler {
  const {
    model = 'gpt-4o-mini',
    systemPrompt = 'You are a helpful assistant.',
    temperature = 0.7,
    maxTokens,
    streaming = false,
  } = config;

  if (streaming) {
    return async function* (params: Record<string, unknown>) {
      let OpenAI: new () => {
        chat: { completions: { create(p: Record<string, unknown>): Promise<AsyncIterable<Record<string, unknown>>> } };
      };
      try {
        // @ts-ignore — openai is an optional peer dependency
        const mod = await import('openai');
        OpenAI = mod.default;
      } catch {
        throw new Error("OpenAI integration requires the 'openai' package. Install it with: npm install openai");
      }

      const client = new OpenAI();
      const userMessage = extractUserMessage(params);
      const messages = [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: userMessage },
      ];

      const createParams: Record<string, unknown> = { model, messages, temperature, stream: true };
      if (maxTokens != null) createParams.max_tokens = maxTokens;

      const stream = await client.chat.completions.create(createParams);
      for await (const chunk of stream) {
        const choices = (chunk as Record<string, unknown>).choices as Array<Record<string, unknown>> | undefined;
        const delta = choices?.[0]?.delta as Record<string, unknown> | undefined;
        const content = delta?.content as string | undefined;
        if (content) yield content;
      }
    };
  }

  return async (params: Record<string, unknown>): Promise<string> => {
    let OpenAI: new () => {
      chat: { completions: { create(p: Record<string, unknown>): Promise<Record<string, unknown>> } };
    };
    try {
      // @ts-ignore — openai is an optional peer dependency
      const mod = await import('openai');
      OpenAI = mod.default;
    } catch {
      throw new Error("OpenAI integration requires the 'openai' package. Install it with: npm install openai");
    }

    const client = new OpenAI();
    const userMessage = extractUserMessage(params);
    const messages = [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userMessage },
    ];

    const createParams: Record<string, unknown> = { model, messages, temperature };
    if (maxTokens != null) createParams.max_tokens = maxTokens;

    const response = await client.chat.completions.create(createParams);
    const choices = response.choices as Array<Record<string, unknown>> | undefined;
    const message = choices?.[0]?.message as Record<string, unknown> | undefined;
    return (message?.content as string) ?? '';
  };
}

/**
 * Returns a SkillHandler that calls the Anthropic messages API.
 *
 * Requires: npm install @anthropic-ai/sdk
 *
 * @example
 *   agent.skill("analyze", anthropicSkill({ model: "claude-sonnet-4-6" }));
 */
export function anthropicSkill(config: AnthropicSkillConfig = {}): SkillHandler {
  const {
    model = 'claude-sonnet-4-6',
    systemPrompt = 'You are a helpful assistant.',
    temperature = 0.7,
    maxTokens = 1024,
    streaming = false,
  } = config;

  if (streaming) {
    return async function* (params: Record<string, unknown>) {
      let Anthropic: new () => {
        messages: { stream(p: Record<string, unknown>): AsyncIterable<Record<string, unknown>> };
      };
      try {
        // @ts-ignore — @anthropic-ai/sdk is an optional peer dependency
        const mod = await import('@anthropic-ai/sdk');
        Anthropic = mod.default;
      } catch {
        throw new Error(
          "Anthropic integration requires the '@anthropic-ai/sdk' package. Install it with: npm install @anthropic-ai/sdk",
        );
      }

      const client = new Anthropic();
      const userMessage = extractUserMessage(params);

      const stream = client.messages.stream({
        model,
        system: systemPrompt,
        messages: [{ role: 'user', content: userMessage }],
        max_tokens: maxTokens,
        temperature,
      });

      for await (const event of stream) {
        const delta = (event as Record<string, unknown>).delta as Record<string, unknown> | undefined;
        const text = delta?.text as string | undefined;
        if (text) yield text;
      }
    };
  }

  return async (params: Record<string, unknown>): Promise<string> => {
    let Anthropic: new () => { messages: { create(p: Record<string, unknown>): Promise<Record<string, unknown>> } };
    try {
      // @ts-ignore — @anthropic-ai/sdk is an optional peer dependency
      const mod = await import('@anthropic-ai/sdk');
      Anthropic = mod.default;
    } catch {
      throw new Error(
        "Anthropic integration requires the '@anthropic-ai/sdk' package. Install it with: npm install @anthropic-ai/sdk",
      );
    }

    const client = new Anthropic();
    const userMessage = extractUserMessage(params);

    const response = await client.messages.create({
      model,
      system: systemPrompt,
      messages: [{ role: 'user', content: userMessage }],
      max_tokens: maxTokens,
      temperature,
    });

    const content = response.content as Array<Record<string, unknown>>;
    return content
      .filter((block) => block.type === 'text')
      .map((block) => block.text as string)
      .join('');
  };
}

export interface OllamaSkillConfig {
  model?: string;
  baseUrl?: string;
  systemPrompt?: string;
  temperature?: number;
  streaming?: boolean;
}

/**
 * Returns a SkillHandler that calls a local Ollama instance.
 *
 * No extra packages needed — uses native fetch (Node 18+).
 *
 * @example
 *   agent.skill("chat", ollamaSkill({ model: "llama3.2" }));
 */
export function ollamaSkill(config: OllamaSkillConfig = {}): SkillHandler {
  const {
    model = 'llama3.2',
    baseUrl = 'http://localhost:11434',
    systemPrompt = 'You are a helpful assistant.',
    temperature = 0.7,
    streaming = false,
  } = config;

  const url = `${baseUrl.replace(/\/$/, '')}/api/chat`;
  const buildPayload = (userMessage: string, stream: boolean) => ({
    model,
    messages: [
      { role: 'system', content: systemPrompt },
      { role: 'user', content: userMessage },
    ],
    stream,
    options: { temperature },
  });

  if (streaming) {
    return async function* (params: Record<string, unknown>) {
      const userMessage = extractUserMessage(params);
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(buildPayload(userMessage, true)),
      });
      if (!response.ok || !response.body) {
        throw new Error(`Ollama returned HTTP ${response.status}`);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';
        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line) as Record<string, unknown>;
            const content = (data.message as Record<string, unknown>)?.content as string;
            if (content) yield content;
          } catch {
            /* skip malformed lines */
          }
        }
      }
    };
  }

  return async (params: Record<string, unknown>): Promise<string> => {
    const userMessage = extractUserMessage(params);
    const response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(buildPayload(userMessage, false)),
    });
    if (!response.ok) throw new Error(`Ollama returned HTTP ${response.status}`);
    const data = (await response.json()) as Record<string, unknown>;
    return ((data.message as Record<string, unknown>)?.content as string) ?? '';
  };
}

export interface BedrockSkillConfig {
  model?: string;
  region?: string;
  systemPrompt?: string;
  temperature?: number;
  maxTokens?: number;
  streaming?: boolean;
}

/**
 * Returns a SkillHandler that calls the AWS Bedrock Converse API.
 *
 * Works with any Bedrock model (Claude, Llama, Mistral, Nova, etc.)
 *
 * Requires: npm install @aws-sdk/client-bedrock-runtime
 *
 * @example
 *   agent.skill("chat", bedrockSkill({ model: "anthropic.claude-3-haiku-20240307-v1:0" }));
 */
export function bedrockSkill(config: BedrockSkillConfig = {}): SkillHandler {
  const {
    model = 'anthropic.claude-3-haiku-20240307-v1:0',
    region = 'us-east-1',
    systemPrompt = 'You are a helpful assistant.',
    temperature = 0.7,
    maxTokens = 1024,
    streaming = false,
  } = config;

  // Optional peer dependency: @aws-sdk/client-bedrock-runtime is not installed at compile time.
  // We use a structural type that matches the subset of BedrockRuntimeClient we need.
  interface BedrockClient {
    send(command: unknown): Promise<Record<string, unknown>>;
  }

  async function getClient(): Promise<BedrockClient> {
    try {
      // @ts-ignore — @aws-sdk/client-bedrock-runtime is an optional peer dependency
      const { BedrockRuntimeClient } = await import('@aws-sdk/client-bedrock-runtime');
      return new BedrockRuntimeClient({ region }) as BedrockClient;
    } catch {
      throw new Error(
        "Bedrock integration requires '@aws-sdk/client-bedrock-runtime'. " +
          'Install it with: npm install @aws-sdk/client-bedrock-runtime',
      );
    }
  }

  if (streaming) {
    return async function* (params: Record<string, unknown>) {
      // @ts-ignore — @aws-sdk/client-bedrock-runtime is an optional peer dependency
      const { ConverseStreamCommand } = await import('@aws-sdk/client-bedrock-runtime').catch(() => {
        throw new Error(
          "Bedrock integration requires '@aws-sdk/client-bedrock-runtime'. " +
            'Install it with: npm install @aws-sdk/client-bedrock-runtime',
        );
      });
      const client = await getClient();
      const userMessage = extractUserMessage(params);
      const command = new ConverseStreamCommand({
        modelId: model,
        system: [{ text: systemPrompt }],
        messages: [{ role: 'user', content: [{ text: userMessage }] }],
        inferenceConfig: { maxTokens, temperature },
      });
      const response = await client.send(command);
      const stream = response['stream'] as AsyncIterable<Record<string, unknown>> | undefined;
      for await (const event of stream ?? []) {
        const delta = (event['contentBlockDelta'] as Record<string, unknown> | undefined)?.['delta'] as
          | Record<string, unknown>
          | undefined;
        const text = delta?.['text'] as string | undefined;
        if (text) yield text;
      }
    };
  }

  return async (params: Record<string, unknown>): Promise<string> => {
    // @ts-ignore — @aws-sdk/client-bedrock-runtime is an optional peer dependency
    const { ConverseCommand } = await import('@aws-sdk/client-bedrock-runtime').catch(() => {
      throw new Error(
        "Bedrock integration requires '@aws-sdk/client-bedrock-runtime'. " +
          'Install it with: npm install @aws-sdk/client-bedrock-runtime',
      );
    });
    const client = await getClient();
    const userMessage = extractUserMessage(params);
    const command = new ConverseCommand({
      modelId: model,
      system: [{ text: systemPrompt }],
      messages: [{ role: 'user', content: [{ text: userMessage }] }],
      inferenceConfig: { maxTokens, temperature },
    });
    const response = await client.send(command);
    const output = response['output'] as Record<string, unknown> | undefined;
    const message = output?.['message'] as Record<string, unknown> | undefined;
    const content = (message?.['content'] as Array<Record<string, unknown>> | undefined) ?? [];
    return content
      .filter((b: Record<string, unknown>) => b['text'] != null)
      .map((b: Record<string, unknown>) => b['text'] as string)
      .join('');
  };
}

function extractUserMessage(params: Record<string, unknown>): string {
  for (const key of ['message', 'text', 'query', 'prompt', 'input']) {
    if (key in params) return String(params[key]);
  }
  const first = Object.values(params)[0];
  return first != null ? String(first) : '';
}
