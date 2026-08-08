/**
 * Multi-agent orchestration for A2A Lite TypeScript.
 * Mirrors Python's orchestration.py for cross-language consistency.
 */

import { v4 as uuidv4 } from 'uuid';
import { RemoteAgentError } from './errors.js';

/** A2A v1.0 version header — required: without it 1.x servers assume 0.3 and reject. */
const A2A_VERSION_HEADERS = { 'A2A-Version': '1.0' } as const;

/** Terminal task states in the A2A v1.0 wire format. */
const TERMINAL_STATES = new Set([
  'TASK_STATE_COMPLETED',
  'TASK_STATE_FAILED',
  'TASK_STATE_CANCELED',
  'TASK_STATE_REJECTED',
  'TASK_STATE_INPUT_REQUIRED',
  'TASK_STATE_AUTH_REQUIRED',
]);

/** Extract text from a v1.0 wire part (`{ "text": ... }`). */
function partText(part: Record<string, unknown>): string {
  return typeof part.text === 'string' ? part.text : '';
}

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
// discoverAgent — fetch /.well-known/agent-card.json from a remote agent
// ---------------------------------------------------------------------------

export async function discoverAgent(agentUrl: string, timeout = 30000): Promise<AgentCardInfo> {
  const base = agentUrl.replace(/\/$/, '');
  const url = `${base}/.well-known/agent-card.json`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new RemoteAgentError(`Failed to discover agent at ${url}: HTTP ${response.status}`, {
        status: response.status,
      });
    }

    const raw = (await response.json()) as Record<string, unknown>;

    // Detect A2A 0.3 cards (root `url` + `protocolVersion`, no supportedInterfaces)
    if (!('supportedInterfaces' in raw) && ('url' in raw || 'protocolVersion' in raw)) {
      throw new RemoteAgentError(`Agent at ${agentUrl} speaks A2A 0.3, not supported by a2a-lite 1.0`, raw);
    }

    const interfaces = (raw.supportedInterfaces ?? []) as Array<Record<string, unknown>>;
    const interfaceUrl = interfaces.length > 0 ? ((interfaces[0].url as string) ?? agentUrl) : agentUrl;

    const capabilities = (raw.capabilities ?? {}) as Record<string, unknown>;
    const skills = (raw.skills ?? []) as Array<Record<string, unknown>>;

    return {
      name: (raw.name as string) ?? 'unknown',
      description: (raw.description as string) ?? '',
      url: interfaceUrl,
      version: (raw.version as string) ?? '0.0.0',
      skills: skills.map((s) => ({
        id: (s.id as string) ?? (s.name as string) ?? '',
        name: (s.name as string) ?? (s.id as string) ?? '',
        description: (s.description as string) ?? '',
      })),
      supportsStreaming: !!capabilities.streaming,
      supportsPush: !!capabilities.pushNotifications,
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
  return sendJsonRpc(agentUrl, 'GetTask', { id: taskId }, timeout);
}

export async function cancelRemoteTask(agentUrl: string, taskId: string, timeout = 30000): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'CancelTask', { id: taskId }, timeout);
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
    'CreateTaskPushNotificationConfig',
    { taskId, url: webhookUrl, ...(token ? { token } : {}) },
    timeout,
  );
}

export async function getTaskPushNotification(agentUrl: string, taskId: string, timeout = 10000): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'GetTaskPushNotificationConfig', { taskId }, timeout);
}

export async function deleteTaskPushNotification(agentUrl: string, taskId: string, timeout = 10000): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'DeleteTaskPushNotificationConfig', { taskId }, timeout);
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
      headers: { 'Content-Type': 'application/json', ...A2A_VERSION_HEADERS },
      body: JSON.stringify(requestBody),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new RemoteAgentError(`Remote agent returned HTTP ${response.status}`, { status: response.status });
    }

    const data = (await response.json()) as Record<string, unknown>;

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

  async broadcast(
    skill: string,
    params: Record<string, unknown> = {},
    timeout = 30000,
  ): Promise<Record<string, unknown>> {
    const results: Record<string, unknown> = {};
    await Promise.all(
      [...this.agents.entries()].map(async ([name, url]) => {
        try {
          const { result } = await callRemoteSkillInternal(url, skill, params, timeout);
          results[name] = result;
        } catch (err) {
          results[name] = { error: (err as Error).message, type: (err as Error).constructor.name };
        }
      }),
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
    method: 'SendMessage',
    id: uuidv4().replace(/-/g, ''),
    params: {
      message: {
        role: 'ROLE_USER',
        parts: [{ text: message }],
        messageId: uuidv4().replace(/-/g, ''),
      },
    },
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(agentUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...A2A_VERSION_HEADERS },
      body: JSON.stringify(requestBody),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new RemoteAgentError(`Remote agent returned HTTP ${response.status}`, { status: response.status });
    }

    const data = (await response.json()) as Record<string, unknown>;
    const result = extractResult(data);

    // Extract task ID from the A2A v1.0 response envelope:
    // result.task.id or result.message.taskId (fallback: random UUID)
    const resultObj = (data.result ?? {}) as Record<string, unknown>;
    const taskObj = (resultObj.task ?? {}) as Record<string, unknown>;
    const messageObj = (resultObj.message ?? {}) as Record<string, unknown>;
    const taskId =
      (typeof taskObj.id === 'string' && taskObj.id) ||
      (typeof messageObj.taskId === 'string' && messageObj.taskId) ||
      (typeof resultObj.id === 'string' && resultObj.id) ||
      uuidv4();

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
    method: 'SendStreamingMessage',
    id: uuidv4().replace(/-/g, ''),
    params: {
      message: {
        role: 'ROLE_USER',
        parts: [{ text: message }],
        messageId: uuidv4().replace(/-/g, ''),
      },
    },
  };

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await fetch(agentUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...A2A_VERSION_HEADERS },
      body: JSON.stringify(requestBody),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new RemoteAgentError(`Remote agent returned HTTP ${response.status}`, { status: response.status });
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

          let data: Record<string, unknown>;
          try {
            data = JSON.parse(jsonStr) as Record<string, unknown>;
          } catch {
            continue;
          }

          // A2A v1.0 SSE events: {"result": {"task"|"statusUpdate"|"artifactUpdate"|"message": ...}}
          // No `final` field: a terminal status state (or the stream closing) marks the end.
          const event = (data.result ?? data) as Record<string, unknown>;
          if (typeof event !== 'object' || event === null) continue;

          let status: Record<string, unknown> | undefined;
          if (event.statusUpdate) {
            status = ((event.statusUpdate as Record<string, unknown>).status ?? undefined) as
              | Record<string, unknown>
              | undefined;
          } else if (event.task) {
            status = ((event.task as Record<string, unknown>).status ?? undefined) as
              | Record<string, unknown>
              | undefined;
          }

          const state = (status?.state as string) ?? '';

          // Check for failed status
          if (state === 'TASK_STATE_FAILED') {
            const statusMessage = status?.message as Record<string, unknown> | undefined;
            let errorText = '';
            for (const part of (statusMessage?.parts ?? []) as Array<Record<string, unknown>>) {
              errorText = partText(part);
              if (errorText) break;
            }
            throw new RemoteAgentError(errorText || 'Remote task failed', data);
          }

          // Extract text from artifact update parts
          const artifact = ((event.artifactUpdate as Record<string, unknown> | undefined)?.artifact ?? undefined) as
            | Record<string, unknown>
            | undefined;
          if (artifact) {
            for (const part of (artifact.parts ?? []) as Array<Record<string, unknown>>) {
              const text = partText(part);
              if (text) yield text;
            }
          }

          // Extract text from status message parts
          if (status) {
            const statusMessage = status.message as Record<string, unknown> | undefined;
            if (statusMessage) {
              for (const part of (statusMessage.parts ?? []) as Array<Record<string, unknown>>) {
                const text = partText(part);
                if (text) yield text;
              }
            }
          }

          // Extract text from a direct message event
          const messageEvent = event.message as Record<string, unknown> | undefined;
          if (messageEvent) {
            for (const part of (messageEvent.parts ?? []) as Array<Record<string, unknown>>) {
              const text = partText(part);
              if (text) yield text;
            }
          }

          // Stop on terminal state (stream end also terminates the generator)
          if (TERMINAL_STATES.has(state)) {
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

  // A2A v1.0: result is { message: {...} } or { task: {...} }
  const envelope = (response.result ?? {}) as Record<string, unknown>;
  const result = (envelope.message ?? envelope.task ?? envelope) as Record<string, unknown>;

  // Text parts on the message itself
  const parts = (result.parts ?? []) as Array<Record<string, unknown>>;
  for (const part of parts) {
    const text = partText(part);
    if (text) {
      try {
        return JSON.parse(text);
      } catch {
        return text;
      }
    }
  }

  // Task results: status message, then artifact parts
  const statusMessage = ((result.status as Record<string, unknown> | undefined)?.message ?? undefined) as
    | Record<string, unknown>
    | undefined;
  for (const part of (statusMessage?.parts ?? []) as Array<Record<string, unknown>>) {
    const text = partText(part);
    if (text) {
      try {
        return JSON.parse(text);
      } catch {
        return text;
      }
    }
  }

  const artifacts = (result.artifacts ?? []) as Array<Record<string, unknown>>;
  for (const artifact of artifacts) {
    for (const part of (artifact.parts ?? []) as Array<Record<string, unknown>>) {
      const text = partText(part);
      if (text) {
        try {
          return JSON.parse(text);
        } catch {
          return text;
        }
      }
    }
  }

  return result;
}
