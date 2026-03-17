/**
 * Multi-agent orchestration for A2A Lite TypeScript.
 * Mirrors Python's orchestration.py for cross-language consistency.
 */

import { v4 as uuidv4 } from 'uuid';
import { RemoteAgentError } from './errors.js';

export class AgentNetwork {
  private agents: Map<string, string> = new Map();

  constructor(agents?: Record<string, string>) {
    if (agents) {
      for (const [name, url] of Object.entries(agents)) {
        this.agents.set(name, url.replace(/\/$/, ''));
      }
    }
  }

  add(name: string, url: string): void {
    this.agents.set(name, url.replace(/\/$/, ''));
  }

  get(name: string): string | undefined {
    return this.agents.get(name);
  }

  remove(name: string): boolean {
    return this.agents.delete(name);
  }

  list(): Record<string, string> {
    return Object.fromEntries(this.agents);
  }

  async call(name: string, skill: string, params: Record<string, unknown> = {}, timeout = 30000): Promise<unknown> {
    const url = this.agents.get(name);
    if (!url) {
      throw new Error(`Agent '${name}' not found in network. Available: ${[...this.agents.keys()].join(', ')}`);
    }
    return callRemoteSkill(url, skill, params, timeout);
  }

  async broadcast(skill: string, params: Record<string, unknown> = {}, timeout = 30000): Promise<Record<string, unknown>> {
    const results: Record<string, unknown> = {};
    await Promise.all(
      [...this.agents.entries()].map(async ([name, url]) => {
        try {
          results[name] = await callRemoteSkill(url, skill, params, timeout);
        } catch (err) {
          results[name] = { error: (err as Error).message, type: (err as Error).constructor.name };
        }
      })
    );
    return results;
  }

  get size(): number {
    return this.agents.size;
  }
}

export async function callRemoteSkill(
  agentUrl: string,
  skill: string,
  params: Record<string, unknown>,
  timeout = 30000
): Promise<unknown> {
  const message = JSON.stringify({ skill, params });
  const requestBody = {
    jsonrpc: '2.0',
    method: 'message/send',
    id: uuidv4().replace(/-/g, ''),
    params: {
      message: {
        role: 'user',
        parts: [{ type: 'text', text: message }],
        messageId: uuidv4().replace(/-/g, ''),
      },
    },
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(agentUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new RemoteAgentError(`Remote agent returned HTTP ${response.status}`, { status: response.status });
    }

    const data = await response.json() as Record<string, unknown>;
    return extractResult(data);
  } finally {
    clearTimeout(timeoutId);
  }
}

function extractResult(response: Record<string, unknown>): unknown {
  if ('error' in response) {
    const error = response.error;
    const message = typeof error === 'string' ? error : JSON.stringify(error);
    throw new RemoteAgentError(message, response);
  }

  const result = (response.result ?? {}) as Record<string, unknown>;
  const parts = (result.parts ?? []) as Array<Record<string, unknown>>;

  for (const part of parts) {
    if (part.kind === 'text' || part.type === 'text') {
      const text = part.text as string;
      try {
        return JSON.parse(text);
      } catch {
        return text;
      }
    }
  }

  return result;
}
