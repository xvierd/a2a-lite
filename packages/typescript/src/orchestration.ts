/**
 * Multi-agent orchestration for A2A Lite TypeScript.
 * Mirrors Python's orchestration.py for cross-language consistency.
 */

import { v4 as uuidv4 } from 'uuid';
import { RemoteAgentError } from './errors.js';

// ---------------------------------------------------------------------------
// TaskHandle — wraps a remote task result with its task ID
// ---------------------------------------------------------------------------

export class TaskHandle {
  constructor(
    public readonly taskId: string,
    public readonly result: unknown,
    public readonly agentUrl: string,
  ) {}

  toString(): string {
    return String(this.result);
  }

  async getStatus(timeout?: number): Promise<unknown> {
    return getRemoteTask(this.agentUrl, this.taskId, timeout);
  }

  async cancel(timeout?: number): Promise<unknown> {
    return cancelRemoteTask(this.agentUrl, this.taskId, timeout);
  }

  async subscribe(webhookUrl: string, token?: string, timeout?: number): Promise<unknown> {
    return setTaskPushNotification(this.agentUrl, this.taskId, webhookUrl, token, timeout);
  }

  async unsubscribe(timeout?: number): Promise<unknown> {
    return deleteTaskPushNotification(this.agentUrl, this.taskId, timeout);
  }

  async getPushConfig(timeout?: number): Promise<unknown> {
    return getTaskPushNotification(this.agentUrl, this.taskId, timeout);
  }
}

// ---------------------------------------------------------------------------
// AgentCardInfo — describes a remote agent's capabilities
// ---------------------------------------------------------------------------

export interface AgentCardInfo {
  name: string;
  description: string;
  url: string;
  version: string;
  skills: Array<{ id: string; name: string; description: string }>;
  supportsStreaming: boolean;
  supportsPush: boolean;
  raw: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// discoverAgent — fetch /.well-known/agent.json from a remote agent
// ---------------------------------------------------------------------------

export async function discoverAgent(agentUrl: string, timeout = 30000): Promise<AgentCardInfo> {
  const base = agentUrl.replace(/\/$/, '');
  const url = `${base}/.well-known/agent.json`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new RemoteAgentError(
        `Failed to discover agent at ${url}: HTTP ${response.status}`,
        { status: response.status },
      );
    }

    const raw = await response.json() as Record<string, unknown>;
    const capabilities = (raw.capabilities ?? {}) as Record<string, unknown>;
    const skills = (raw.skills ?? []) as Array<Record<string, unknown>>;

    return {
      name: (raw.name as string) ?? 'unknown',
      description: (raw.description as string) ?? '',
      url: (raw.url as string) ?? agentUrl,
      version: (raw.version as string) ?? '0.0.0',
      skills: skills.map((s) => ({
        id: (s.id as string) ?? (s.name as string) ?? '',
        name: (s.name as string) ?? (s.id as string) ?? '',
        description: (s.description as string) ?? '',
      })),
      supportsStreaming: !!(capabilities.streaming),
      supportsPush: !!(capabilities.pushNotifications),
      raw,
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---------------------------------------------------------------------------
// getRemoteTask / cancelRemoteTask — JSON-RPC helpers
// ---------------------------------------------------------------------------

export async function getRemoteTask(agentUrl: string, taskId: string, timeout = 30000): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'tasks/get', { id: taskId }, timeout);
}

export async function cancelRemoteTask(agentUrl: string, taskId: string, timeout = 30000): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'tasks/cancel', { id: taskId }, timeout);
}

// ---------------------------------------------------------------------------
// Per-task push notification client helpers
// ---------------------------------------------------------------------------

export async function setTaskPushNotification(
  agentUrl: string,
  taskId: string,
  webhookUrl: string,
  token?: string,
  timeout = 10000,
): Promise<unknown> {
  return sendJsonRpc(
    agentUrl,
    'tasks/pushNotification/set',
    { id: taskId, pushNotificationConfig: { url: webhookUrl, ...(token ? { token } : {}) } },
    timeout,
  );
}

export async function getTaskPushNotification(
  agentUrl: string,
  taskId: string,
  timeout = 10000,
): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'tasks/pushNotification/get', { id: taskId }, timeout);
}

export async function deleteTaskPushNotification(
  agentUrl: string,
  taskId: string,
  timeout = 10000,
): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'tasks/pushNotification/delete', { id: taskId }, timeout);
}

async function sendJsonRpc(
  agentUrl: string,
  method: string,
  params: Record<string, unknown>,
  timeout: number,
): Promise<unknown> {
  const requestBody = {
    jsonrpc: '2.0',
    method,
    id: uuidv4().replace(/-/g, ''),
    params,
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

    if ('error' in data) {
      const error = data.error;
      const message = typeof error === 'string' ? error : JSON.stringify(error);
      throw new RemoteAgentError(message, data);
    }

    return data.result;
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---------------------------------------------------------------------------
// AgentNetwork
// ---------------------------------------------------------------------------

export class AgentNetwork {
  private agents: Map<string, string> = new Map();
  private cards: Map<string, AgentCardInfo> = new Map();

  constructor(agents?: Record<string, string>) {
    if (agents) {
      for (const [name, url] of Object.entries(agents)) {
        this.agents.set(name, url.replace(/\/$/, ''));
      }
    }
  }

  add(name: string, url: string, options?: { autoDiscover?: boolean }): void {
    this.agents.set(name, url.replace(/\/$/, ''));
    if (options?.autoDiscover) {
      // Fire-and-forget discovery; errors are silently ignored
      this.discover(name).catch(() => {});
    }
  }

  get(name: string): string | undefined {
    return this.agents.get(name);
  }

  remove(name: string): boolean {
    this.cards.delete(name);
    return this.agents.delete(name);
  }

  list(): Record<string, string> {
    return Object.fromEntries(this.agents);
  }

  getCard(name: string): AgentCardInfo | undefined {
    return this.cards.get(name);
  }

  async discover(name: string): Promise<AgentCardInfo> {
    const url = this.agents.get(name);
    if (!url) {
      throw new Error(`Agent '${name}' not found in network. Available: ${[...this.agents.keys()].join(', ')}`);
    }
    const card = await discoverAgent(url);
    this.cards.set(name, card);
    return card;
  }

  async call(
    name: string,
    skill: string,
    params: Record<string, unknown> = {},
    timeout = 30000,
    options?: { returnHandle?: boolean },
  ): Promise<unknown> {
    const url = this.agents.get(name);
    if (!url) {
      throw new Error(`Agent '${name}' not found in network. Available: ${[...this.agents.keys()].join(', ')}`);
    }

    const { result, taskId } = await callRemoteSkillInternal(url, skill, params, timeout);

    if (options?.returnHandle) {
      return new TaskHandle(taskId, result, url);
    }
    return result;
  }

  async *stream(
    name: string,
    skill: string,
    params: Record<string, unknown> = {},
    timeout = 30000,
  ): AsyncGenerator<string> {
    const url = this.agents.get(name);
    if (!url) {
      throw new Error(`Agent '${name}' not found in network. Available: ${[...this.agents.keys()].join(', ')}`);
    }
    yield* streamRemoteSkill(url, skill, params, timeout);
  }

  async broadcast(skill: string, params: Record<string, unknown> = {}, timeout = 30000): Promise<Record<string, unknown>> {
    const results: Record<string, unknown> = {};
    await Promise.all(
      [...this.agents.entries()].map(async ([name, url]) => {
        try {
          const { result } = await callRemoteSkillInternal(url, skill, params, timeout);
          results[name] = result;
        } catch (err) {
          results[name] = { error: (err as Error).message, type: (err as Error).constructor.name };
        }
      })
    );
    return results;
  }

  async getTask(name: string, taskId: string, timeout?: number): Promise<unknown> {
    const url = this.agents.get(name);
    if (url === undefined) throw new Error(`Agent '${name}' not found in network.`);
    return getRemoteTask(url, taskId, timeout);
  }

  async cancelTask(name: string, taskId: string, timeout?: number): Promise<unknown> {
    const url = this.agents.get(name);
    if (url === undefined) throw new Error(`Agent '${name}' not found in network.`);
    return cancelRemoteTask(url, taskId, timeout);
  }

  get size(): number {
    return this.agents.size;
  }
}

// ---------------------------------------------------------------------------
// callRemoteSkill — public API (backward-compatible, returns just the result)
// ---------------------------------------------------------------------------

export async function callRemoteSkill(
  agentUrl: string,
  skill: string,
  params: Record<string, unknown>,
  timeout = 30000,
): Promise<unknown> {
  const { result } = await callRemoteSkillInternal(agentUrl, skill, params, timeout);
  return result;
}

export async function callRemoteSkillWithHandle(
  agentUrl: string,
  skill: string,
  params: Record<string, unknown>,
  timeout = 30000,
): Promise<TaskHandle> {
  const { result, taskId } = await callRemoteSkillInternal(agentUrl, skill, params, timeout);
  return new TaskHandle(taskId, result, agentUrl);
}

// ---------------------------------------------------------------------------
// callRemoteSkillInternal — returns both result and taskId
// ---------------------------------------------------------------------------

async function callRemoteSkillInternal(
  agentUrl: string,
  skill: string,
  params: Record<string, unknown>,
  timeout: number,
): Promise<{ result: unknown; taskId: string }> {
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
    const result = extractResult(data);

    // Extract task ID from the A2A response envelope
    const resultObj = (data.result ?? {}) as Record<string, unknown>;
    const taskId = typeof resultObj.id === 'string' ? resultObj.id : uuidv4();

    return { result, taskId };
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---------------------------------------------------------------------------
// streamRemoteSkill — SSE streaming consumption
// ---------------------------------------------------------------------------

export async function* streamRemoteSkill(
  agentUrl: string,
  skill: string,
  params: Record<string, unknown> = {},
  timeout = 30000,
): AsyncGenerator<string> {
  const message = JSON.stringify({ skill, params });
  const requestBody = {
    jsonrpc: '2.0',
    method: 'message/stream',
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
      throw new RemoteAgentError(
        `Remote agent returned HTTP ${response.status}`,
        { status: response.status },
      );
    }

    if (!response.body) {
      throw new RemoteAgentError('Response body is empty — streaming not supported');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() ?? '';

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;

          const jsonStr = trimmed.slice(5).trim();
          if (!jsonStr || jsonStr === '[DONE]') continue;

          let event: Record<string, unknown>;
          try {
            event = JSON.parse(jsonStr) as Record<string, unknown>;
          } catch {
            continue;
          }

          // Check for failed status
          const status = event.status as Record<string, unknown> | undefined;
          if (status) {
            const state = status.state as string | undefined;
            if (state === 'failed') {
              const statusMessage = (status.message as Record<string, unknown> | undefined);
              const errorText = statusMessage
                ? String((statusMessage.parts as Array<Record<string, unknown>>)?.[0]?.text ?? 'Remote task failed')
                : 'Remote task failed';
              throw new RemoteAgentError(errorText, event);
            }
            if (state === 'completed' || state === 'canceled' || state === 'rejected') {
              return;
            }
          }

          // Extract text from artifact parts
          const artifact = event.artifact as Record<string, unknown> | undefined;
          if (artifact) {
            const parts = (artifact.parts ?? []) as Array<Record<string, unknown>>;
            for (const part of parts) {
              if ((part.kind === 'text' || part.type === 'text') && typeof part.text === 'string') {
                yield part.text;
              }
            }
          }

          // Stop if this is a final event
          if (event.final === true) {
            return;
          }
        }
      }
    } finally {
      reader.releaseLock();
    }
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
