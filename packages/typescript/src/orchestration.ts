/**
 * Multi-agent orchestration for A2A Lite TypeScript.
 * Mirrors Python's orchestration.py for cross-language consistency.
 */

import { v4 as uuidv4 } from 'uuid';
import { ListTasksResponse, StreamResponse, TaskState, type ListTasksRequest, type Part } from '@a2a-js/sdk';
import { requestJsonRpc, streamJsonRpc } from './json-rpc.js';
import { RemoteAgentError } from './errors.js';
import { parseDiscoveryCard, selectJsonRpcInterface, type DiscoveryCard } from './discovery.js';
import { remoteFetch, bindRemoteOptions, type RemoteCallOptions } from './remote-auth.js';

const TERMINAL_STATES = new Set([
  TaskState.TASK_STATE_COMPLETED,
  TaskState.TASK_STATE_FAILED,
  TaskState.TASK_STATE_CANCELED,
  TaskState.TASK_STATE_REJECTED,
]);

/** SDK-discriminated event, plus its original wire fields (including optional field presence). */
export type RemoteStreamEvent = NonNullable<StreamResponse['payload']> & { raw: Record<string, unknown> };
export type RemoteSkillResult = Extract<RemoteStreamEvent, { $case: 'task' | 'message' }>;
export type TaskListQuery = Partial<Omit<ListTasksRequest, 'tenant' | 'status'>> & {
  status?: keyof typeof TaskState;
};

// ---------------------------------------------------------------------------
// TaskHandle — wraps a remote task result with its task ID
// ---------------------------------------------------------------------------

export class TaskHandle {
  constructor(
    public readonly taskId: string,
    public readonly result: unknown,
    public readonly agentUrl: string,
    private readonly options: RemoteCallOptions = {},
  ) {}

  toString(): string {
    return String(this.result);
  }

  async getStatus(timeout?: number): Promise<unknown> {
    return getRemoteTask(this.agentUrl, this.taskId, timeout, this.options);
  }

  async get(timeout?: number): Promise<unknown> {
    return this.getStatus(timeout);
  }

  async cancel(timeout?: number): Promise<unknown> {
    return cancelRemoteTask(this.agentUrl, this.taskId, timeout, this.options);
  }

  /** Open SubscribeToTask for the current snapshot and subsequent events. */
  streamEvents(timeout?: number): AsyncGenerator<RemoteStreamEvent> {
    return subscribeToTask(this.agentUrl, this.taskId, timeout, this.options);
  }

  async subscribe(webhookUrl: string, token?: string, timeout?: number, configId = this.taskId): Promise<unknown> {
    return setTaskPushNotification(this.agentUrl, this.taskId, webhookUrl, token, timeout, configId, this.options);
  }

  async unsubscribe(timeout?: number, configId = this.taskId): Promise<unknown> {
    return deleteTaskPushNotification(this.agentUrl, this.taskId, timeout, configId, this.options);
  }

  async getPushConfig(timeout?: number, configId = this.taskId): Promise<unknown> {
    return getTaskPushNotification(this.agentUrl, this.taskId, timeout, configId, this.options);
  }
}

function remoteTaskHandle(
  taskId: string | undefined,
  result: unknown,
  agentUrl: string,
  options: RemoteCallOptions = {},
): TaskHandle {
  if (!taskId) {
    throw new RemoteAgentError(
      'Remote agent returned a Message without a task ID; a task handle requires a real remote task.',
    );
  }
  return new TaskHandle(taskId, result, agentUrl, bindRemoteOptions(options, agentUrl));
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
  tenant?: string;
  discoveryUrl?: string;
  supportsStreaming: boolean;
  supportsPush: boolean;
  raw: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// discoverAgent — fetch /.well-known/agent-card.json from a remote agent
// ---------------------------------------------------------------------------

export async function discoverAgent(
  agentUrl: string,
  timeout = 30000,
  options: RemoteCallOptions = {},
): Promise<AgentCardInfo & { raw: DiscoveryCard }> {
  const base = agentUrl.replace(/\/$/, '');
  const url = `${base}/.well-known/agent-card.json`;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);

  try {
    const response = await remoteFetch(url, bindRemoteOptions(options, agentUrl), {
      method: 'GET',
      headers: { Accept: 'application/json', 'A2A-Version': '1.0' },
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new RemoteAgentError(`Failed to discover agent at ${url}: HTTP ${response.status}`, {
        status: response.status,
      });
    }

    const raw = parseDiscoveryCard(await response.json());
    const selected = selectJsonRpcInterface(raw, options.tenant);
    const { capabilities, skills } = raw;

    return {
      name: (raw.name as string) ?? 'unknown',
      description: (raw.description as string) ?? '',
      url: selected.url,
      discoveryUrl: base,
      tenant: selected.tenant,
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

export async function getRemoteTask(
  agentUrl: string,
  taskId: string,
  timeout = 30000,
  options: RemoteCallOptions = {},
): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'GetTask', { id: taskId }, timeout, options);
}

export async function cancelRemoteTask(
  agentUrl: string,
  taskId: string,
  timeout = 30000,
  options: RemoteCallOptions = {},
): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'CancelTask', { id: taskId }, timeout, options);
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
  configId = taskId,
  options: RemoteCallOptions = {},
): Promise<unknown> {
  return sendJsonRpc(
    agentUrl,
    'CreateTaskPushNotificationConfig',
    { taskId, id: configId, url: webhookUrl, ...(token ? { token } : {}) },
    timeout,
    options,
  );
}

export async function getTaskPushNotification(
  agentUrl: string,
  taskId: string,
  timeout = 10000,
  configId = taskId,
  options: RemoteCallOptions = {},
): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'GetTaskPushNotificationConfig', { taskId, id: configId }, timeout, options);
}

export async function deleteTaskPushNotification(
  agentUrl: string,
  taskId: string,
  timeout = 10000,
  configId = taskId,
  options: RemoteCallOptions = {},
): Promise<unknown> {
  return sendJsonRpc(agentUrl, 'DeleteTaskPushNotificationConfig', { taskId, id: configId }, timeout, options);
}

async function sendJsonRpc(
  url: string,
  method: string,
  params: Record<string, unknown>,
  timeout: number,
  options: RemoteCallOptions,
): Promise<unknown> {
  return (await requestJsonRpc(url, method, params, timeout, options)).result;
}

export async function listRemoteTasks(
  agentUrl: string,
  query: TaskListQuery = {},
  timeout = 30000,
  options: RemoteCallOptions = {},
): Promise<ListTasksResponse> {
  const result = await sendJsonRpc(agentUrl, 'ListTasks', query, timeout, options);
  if (
    !result ||
    typeof result !== 'object' ||
    Array.isArray(result) ||
    ('tasks' in result && !Array.isArray(result.tasks))
  ) {
    throw new RemoteAgentError('Invalid ListTasks result.');
  }
  return ListTasksResponse.fromJSON(result);
}

// ---------------------------------------------------------------------------
// AgentNetwork
// ---------------------------------------------------------------------------

export class AgentNetwork {
  private agents = new Map<
    string,
    {
      baseUrl: string;
      credentials: RemoteCallOptions;
      card?: Awaited<ReturnType<typeof discoverAgent>>;
      discovery?: ReturnType<typeof discoverAgent>;
    }
  >();

  constructor(agents: Record<string, string> = {}) {
    for (const [name, url] of Object.entries(agents)) this.add(name, url);
  }

  private registration(name: string) {
    const entry = this.agents.get(name);
    if (!entry) throw new Error(`Agent '${name}' not found in network.`);
    return entry;
  }

  getCredentials(name: string): RemoteCallOptions {
    return { ...this.agents.get(name)?.credentials };
  }

  withCredentials(name: string, options: RemoteCallOptions): this {
    const entry = this.registration(name);
    entry.credentials = bindRemoteOptions(options, entry.baseUrl);
    return this;
  }

  add(name: string, url: string, options?: RemoteCallOptions & { autoDiscover?: boolean }): void {
    const baseUrl = url.replace(/\/$/, '');
    this.agents.set(name, { baseUrl, credentials: options ? bindRemoteOptions(options, baseUrl) : {} });
    if (options?.autoDiscover) this.discover(name).catch(() => {});
  }

  get(name: string): string | undefined {
    const entry = this.agents.get(name);
    return entry?.card?.url ?? entry?.baseUrl;
  }

  remove(name: string): boolean {
    return this.agents.delete(name);
  }

  list(): Record<string, string> {
    return Object.fromEntries([...this.agents].map(([name, entry]) => [name, entry.baseUrl]));
  }

  getCard(name: string): AgentCardInfo | undefined {
    return this.agents.get(name)?.card;
  }

  async discover(name: string): Promise<AgentCardInfo> {
    const entry = this.registration(name);
    const discovery = discoverAgent(entry.baseUrl, 30000, entry.credentials);
    entry.discovery = discovery;
    const card = await discovery;
    if (entry.discovery === discovery) entry.card = card;
    return card;
  }

  /** Resolve one operation. Discovery requests always start at the registered base. */
  async resolve(name: string, overrides: RemoteCallOptions = {}, forDiscovery = false) {
    const entry = this.registration(name);
    const discovered = await entry.discovery;
    if (entry !== this.agents.get(name)) throw new RemoteAgentError('Agent registration changed during discovery.');
    const card = forDiscovery ? undefined : discovered;
    const options = bindRemoteOptions({ ...entry.credentials, ...overrides }, entry.baseUrl);
    if (!card) return { url: entry.baseUrl, options };
    const selected =
      options.tenant && options.tenant !== card.tenant ? selectJsonRpcInterface(card.raw, options.tenant) : card;
    return { url: selected.url, options: { ...options, tenant: selected.tenant } };
  }

  async call(
    name: string,
    skill: string,
    params: Record<string, unknown> | undefined,
    timeout: number | undefined,
    options: RemoteCallOptions & { returnHandle: true },
  ): Promise<TaskHandle>;
  async call(
    name: string,
    skill: string,
    params?: Record<string, unknown>,
    timeout?: number,
    options?: RemoteCallOptions & { returnHandle?: boolean },
  ): Promise<unknown>;
  async call(
    name: string,
    skill: string,
    params: Record<string, unknown> = {},
    timeout = 30000,
    options?: RemoteCallOptions & { returnHandle?: boolean },
  ): Promise<unknown> {
    const target = await this.resolve(name, options);
    return options?.returnHandle
      ? callRemoteSkillWithHandle(target.url, skill, params, timeout, target.options)
      : callRemoteSkill(target.url, skill, params, timeout, target.options);
  }

  async callResult(
    name: string,
    skill: string,
    params: Record<string, unknown> = {},
    timeout = 30000,
    options?: RemoteCallOptions,
  ): Promise<RemoteSkillResult> {
    const target = await this.resolve(name, options);
    return callRemoteSkillResult(target.url, skill, params, timeout, target.options);
  }

  async *stream(
    name: string,
    skill: string,
    params: Record<string, unknown> = {},
    timeout = 30000,
    options?: RemoteCallOptions,
  ): AsyncGenerator<string> {
    const target = await this.resolve(name, options);
    yield* streamRemoteSkill(target.url, skill, params, timeout, target.options);
  }

  async *streamEvents(
    name: string,
    skill: string,
    params: Record<string, unknown> = {},
    timeout = 30000,
    options?: RemoteCallOptions,
  ): AsyncGenerator<RemoteStreamEvent> {
    const target = await this.resolve(name, options);
    yield* streamRemoteSkillEvents(target.url, skill, params, timeout, target.options);
  }

  async broadcast(
    skill: string,
    params: Record<string, unknown> = {},
    timeout = 30000,
  ): Promise<Record<string, unknown>> {
    const results: Record<string, unknown> = {};
    await Promise.all(
      [...this.agents.keys()].map(async (name) => {
        try {
          results[name] = await this.call(name, skill, params, timeout);
        } catch (err) {
          results[name] = { error: (err as Error).message, type: (err as Error).constructor.name };
        }
      }),
    );
    return results;
  }

  async getTask(name: string, taskId: string, timeout?: number, options?: RemoteCallOptions): Promise<unknown> {
    const target = await this.resolve(name, options);
    return getRemoteTask(target.url, taskId, timeout, target.options);
  }

  async cancelTask(name: string, taskId: string, timeout?: number, options?: RemoteCallOptions): Promise<unknown> {
    const target = await this.resolve(name, options);
    return cancelRemoteTask(target.url, taskId, timeout, target.options);
  }

  async listTasks(
    name: string,
    query: TaskListQuery = {},
    timeout?: number,
    options?: RemoteCallOptions,
  ): Promise<ListTasksResponse> {
    const target = await this.resolve(name, options);
    return listRemoteTasks(target.url, query, timeout, target.options);
  }

  async *subscribeToTask(name: string, taskId: string, timeout?: number, options?: RemoteCallOptions) {
    const target = await this.resolve(name, options);
    yield* subscribeToTask(target.url, taskId, timeout, target.options);
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
  options: RemoteCallOptions = {},
): Promise<unknown> {
  const { result } = await sendSkillRequest(agentUrl, skill, params, timeout, options);
  return extractResult(result);
}

export async function callRemoteSkillResult(
  agentUrl: string,
  skill: string,
  params: Record<string, unknown> = {},
  timeout = 30000,
  options: RemoteCallOptions = {},
): Promise<RemoteSkillResult> {
  const { result } = await sendSkillRequest(agentUrl, skill, params, timeout, options);
  const event = decodeEvent(result);
  if (event.$case !== 'message' && event.$case !== 'task') throw new RemoteAgentError('Expected a Message or Task.');
  return event;
}

export async function callRemoteSkillWithHandle(
  agentUrl: string,
  skill: string,
  params: Record<string, unknown>,
  timeout = 30000,
  options: RemoteCallOptions = {},
): Promise<TaskHandle> {
  const { result } = await sendSkillRequest(agentUrl, skill, params, timeout, options);
  const envelope = result as { task?: { id?: unknown }; message?: { taskId?: unknown } } | null;
  const taskId = envelope?.task?.id ?? envelope?.message?.taskId;
  return remoteTaskHandle(
    typeof taskId === 'string' && taskId.trim() ? taskId : undefined,
    extractResult(result),
    agentUrl,
    options,
  );
}

function skillMessage(skill: string, params: Record<string, unknown>, options: RemoteCallOptions) {
  return {
    ...(options.returnImmediately ? { configuration: { returnImmediately: true } } : {}),
    message: {
      taskId: options.taskId,
      role: 'ROLE_USER',
      parts: [{ text: JSON.stringify({ skill, params }) }],
      messageId: uuidv4().replace(/-/g, ''),
    },
  };
}

/** Shared by the CLI (which prints the full envelope) and the public skill helpers. */
export function sendSkillRequest(
  url: string,
  skill: string,
  params: Record<string, unknown>,
  timeout: number,
  options: RemoteCallOptions,
) {
  return requestJsonRpc(url, 'SendMessage', skillMessage(skill, params, options), timeout, options);
}

function decodeEvent(raw: unknown): RemoteStreamEvent {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw))
    throw new RemoteAgentError('Expected an A2A response object.');
  const payload = StreamResponse.fromJSON(raw).payload;
  if (!payload) throw new RemoteAgentError('Missing A2A response payload.');
  return { ...payload, raw: raw as Record<string, unknown> };
}

async function* streamEvents(
  url: string,
  method: 'SubscribeToTask' | 'SendStreamingMessage',
  params: Record<string, unknown>,
  timeout: number,
  options: RemoteCallOptions,
): AsyncGenerator<RemoteStreamEvent> {
  let needsSnapshot = method === 'SubscribeToTask';
  let interrupted = false;
  for await (const raw of streamJsonRpc(url, method, params, timeout, options)) {
    const payload = decodeEvent(raw);
    if (method === 'SubscribeToTask') {
      if (needsSnapshot && payload.$case !== 'task')
        throw new RemoteAgentError('Subscription must start with a Task snapshot.');
      if (payload.$case === 'message') throw new RemoteAgentError('Unexpected Message in task subscription.');
      const taskId = payload.$case === 'task' ? payload.value.id : payload.value.taskId;
      if (taskId !== params.id) throw new RemoteAgentError('Subscription task ID mismatch.');
      needsSnapshot = false;
    }
    const status = payload.$case === 'task' || payload.$case === 'statusUpdate' ? payload.value.status : undefined;
    if (status) {
      interrupted =
        status.state === TaskState.TASK_STATE_INPUT_REQUIRED || status.state === TaskState.TASK_STATE_AUTH_REQUIRED;
    }
    yield payload;
    if (payload.$case === 'message' || (status && TERMINAL_STATES.has(status.state))) return;
  }
  if (!interrupted) throw new RemoteAgentError('SSE stream closed before a final message or task state.');
}

export function subscribeToTask(
  agentUrl: string,
  taskId: string,
  timeout = 30000,
  options: RemoteCallOptions = {},
): AsyncGenerator<RemoteStreamEvent> {
  return streamEvents(agentUrl, 'SubscribeToTask', { id: taskId }, timeout, options);
}

export function streamRemoteSkillEvents(
  agentUrl: string,
  skill: string,
  params: Record<string, unknown> = {},
  timeout = 30000,
  options: RemoteCallOptions = {},
): AsyncGenerator<RemoteStreamEvent> {
  return streamEvents(agentUrl, 'SendStreamingMessage', skillMessage(skill, params, options), timeout, options);
}

function* textParts(parts: Part[] = []) {
  for (const part of parts) {
    if (part.content?.$case === 'text' && part.content.value) yield part.content.value;
  }
}

export async function* streamRemoteSkill(
  agentUrl: string,
  skill: string,
  params: Record<string, unknown> = {},
  timeout = 30000,
  options: RemoteCallOptions = {},
): AsyncGenerator<string> {
  for await (const event of streamRemoteSkillEvents(agentUrl, skill, params, timeout, options)) {
    if (event.$case === 'message') {
      yield* textParts(event.value.parts);
    } else if (event.$case === 'artifactUpdate') {
      yield* textParts(event.value.artifact?.parts);
    } else {
      const status = event.value.status;
      if (status?.state === TaskState.TASK_STATE_FAILED) {
        throw new RemoteAgentError(textParts(status.message?.parts).next().value || 'Remote task failed', {
          result: event.raw,
        });
      }
      yield* textParts(status?.message?.parts);
    }
  }
}

function extractResult(raw: unknown): unknown {
  if (!raw || typeof raw !== 'object') return raw;
  const envelope = raw as Record<string, unknown>;
  const result = (envelope.message ?? envelope.task ?? envelope) as Record<string, unknown>;
  const status = result.status as { message?: { parts?: Array<{ text?: string }> } } | undefined;
  const artifacts = (result.artifacts ?? []) as Array<{ parts?: Array<{ text?: string }> }>;
  for (const parts of [result.parts, status?.message?.parts, ...artifacts.map((a) => a.parts)]) {
    if (!Array.isArray(parts)) continue;
    for (const part of parts) {
      if (typeof part?.text === 'string' && part.text) {
        try {
          return JSON.parse(part.text);
        } catch {
          return part.text;
        }
      }
    }
  }
  return result;
}
