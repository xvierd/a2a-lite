import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  TaskHandle,
  AgentNetwork,
  getRemoteTask,
  cancelRemoteTask,
  discoverAgent,
} from '../src/orchestration.js';
import type { AgentCardInfo } from '../src/orchestration.js';
import { RemoteAgentError } from '../src/errors.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockJsonResponse(body: Record<string, unknown>, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(body),
  } as Response;
}

function a2aResponse(text: string, taskId = 'task-abc-123'): Record<string, unknown> {
  return {
    jsonrpc: '2.0',
    id: '1',
    result: {
      task: {
        id: taskId,
        status: { state: 'TASK_STATE_COMPLETED' },
        artifacts: [],
      },
      message: { taskId, parts: [{ text }] },
    },
  };
}

function agentCardResponse(): Record<string, unknown> {
  return {
    name: 'TestAgent',
    description: 'A test agent',
    version: '1.2.0',
    supportedInterfaces: [
      { url: 'http://test-agent:8787', protocolBinding: 'JSONRPC', protocolVersion: '1.0' },
      { url: 'http://test-agent:8787', protocolBinding: 'HTTP+JSON', protocolVersion: '1.0' },
    ],
    capabilities: {
      streaming: true,
      pushNotifications: false,
    },
    defaultInputModes: ['application/json'],
    defaultOutputModes: ['application/json'],
    skills: [
      { id: 'greet', name: 'greet', description: 'Says hello' },
      { id: 'calc', name: 'calc', description: 'Does math' },
    ],
  };
}

// ---------------------------------------------------------------------------
// TaskHandle
// ---------------------------------------------------------------------------

describe('TaskHandle', () => {
  it('stores taskId, result, and agentUrl', () => {
    const handle = new TaskHandle('t1', { answer: 42 }, 'http://agent:8787');
    expect(handle.taskId).toBe('t1');
    expect(handle.result).toEqual({ answer: 42 });
  });

  it('toString() returns string representation of result', () => {
    expect(new TaskHandle('t1', 'hello', 'http://a').toString()).toBe('hello');
    expect(new TaskHandle('t1', 42, 'http://a').toString()).toBe('42');
    expect(new TaskHandle('t1', { a: 1 }, 'http://a').toString()).toBe('[object Object]');
  });

  it('exposes agentUrl as a readonly property', () => {
    const handle = new TaskHandle('t1', 'ok', 'http://agent:8787');
    expect(handle.agentUrl).toBe('http://agent:8787');
  });
});

// ---------------------------------------------------------------------------
// TaskHandle.getStatus() and TaskHandle.cancel()
// ---------------------------------------------------------------------------

describe('TaskHandle.getStatus()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends a GetTask JSON-RPC request to the correct URL', async () => {
    const body = { jsonrpc: '2.0', id: '1', result: { id: 'task-1', status: { state: 'TASK_STATE_COMPLETED' } } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const handle = new TaskHandle('task-1', 'original-result', 'http://agent:8787');
    const status = await handle.getStatus();

    expect(status).toEqual({ id: 'task-1', status: { state: 'TASK_STATE_COMPLETED' } });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://agent:8787');
    const reqBody = JSON.parse(init.body as string);
    expect(reqBody.method).toBe('GetTask');
    expect(reqBody.params.id).toBe('task-1');
  });
});

describe('TaskHandle.cancel()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends a CancelTask JSON-RPC request to the correct URL', async () => {
    const body = { jsonrpc: '2.0', id: '1', result: { id: 'task-1', status: { state: 'TASK_STATE_CANCELED' } } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const handle = new TaskHandle('task-1', 'original-result', 'http://agent:8787');
    const result = await handle.cancel();

    expect(result).toEqual({ id: 'task-1', status: { state: 'TASK_STATE_CANCELED' } });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://agent:8787');
    const reqBody = JSON.parse(init.body as string);
    expect(reqBody.method).toBe('CancelTask');
    expect(reqBody.params.id).toBe('task-1');
  });
});

// ---------------------------------------------------------------------------
// AgentNetwork.call() with returnHandle
// ---------------------------------------------------------------------------

describe('AgentNetwork.call() with returnHandle', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('returns a TaskHandle when returnHandle is true', async () => {
    const body = a2aResponse('"pong"', 'task-xyz');
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const net = new AgentNetwork({ bot: 'http://bot:3000' });
    const handle = await net.call('bot', 'ping', {}, 30000, { returnHandle: true });

    expect(handle).toBeInstanceOf(TaskHandle);
    const th = handle as TaskHandle;
    expect(th.taskId).toBe('task-xyz');
    expect(th.result).toBe('pong');
  });

  it('returns raw result when returnHandle is not set (backward compat)', async () => {
    const body = a2aResponse('"pong"');
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const net = new AgentNetwork({ bot: 'http://bot:3000' });
    const result = await net.call('bot', 'ping');

    expect(result).toBe('pong');
    expect(result).not.toBeInstanceOf(TaskHandle);
  });

  it('returns raw result when returnHandle is false', async () => {
    const body = a2aResponse('{"v":1}');
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const net = new AgentNetwork({ bot: 'http://bot:3000' });
    const result = await net.call('bot', 'ping', {}, 30000, { returnHandle: false });

    expect(result).toEqual({ v: 1 });
    expect(result).not.toBeInstanceOf(TaskHandle);
  });

  it('generates a UUID taskId when response has no task id', async () => {
    const body = {
      jsonrpc: '2.0',
      id: '1',
      result: { message: { parts: [{ text: '"ok"' }] } },
    };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const net = new AgentNetwork({ bot: 'http://bot:3000' });
    const handle = await net.call('bot', 'ping', {}, 30000, { returnHandle: true });
    const th = handle as TaskHandle;

    expect(th.taskId).toBeTruthy();
    expect(typeof th.taskId).toBe('string');
    expect(th.taskId.length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// getRemoteTask() and cancelRemoteTask()
// ---------------------------------------------------------------------------

describe('getRemoteTask()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends a GetTask JSON-RPC request', async () => {
    const body = { jsonrpc: '2.0', id: '1', result: { id: 'task-1', status: { state: 'TASK_STATE_COMPLETED' } } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const result = await getRemoteTask('http://agent:8787', 'task-1');

    expect(result).toEqual({ id: 'task-1', status: { state: 'TASK_STATE_COMPLETED' } });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const reqBody = JSON.parse(init.body as string);
    expect(reqBody.method).toBe('GetTask');
    expect(reqBody.params.id).toBe('task-1');
  });

  it('throws RemoteAgentError on HTTP error', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse({}, 500));

    await expect(getRemoteTask('http://agent', 'task-1')).rejects.toThrow(RemoteAgentError);
  });

  it('throws RemoteAgentError when response contains error field', async () => {
    const body = { jsonrpc: '2.0', id: '1', error: { code: -32601, message: 'Method not found' } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    await expect(getRemoteTask('http://agent', 'task-1')).rejects.toThrow(RemoteAgentError);
  });
});

describe('cancelRemoteTask()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends a CancelTask JSON-RPC request', async () => {
    const body = { jsonrpc: '2.0', id: '1', result: { id: 'task-1', status: { state: 'TASK_STATE_CANCELED' } } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const result = await cancelRemoteTask('http://agent:8787', 'task-1');

    expect(result).toEqual({ id: 'task-1', status: { state: 'TASK_STATE_CANCELED' } });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const reqBody = JSON.parse(init.body as string);
    expect(reqBody.method).toBe('CancelTask');
    expect(reqBody.params.id).toBe('task-1');
  });
});

// ---------------------------------------------------------------------------
// discoverAgent()
// ---------------------------------------------------------------------------

describe('discoverAgent()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('fetches /.well-known/agent-card.json and returns AgentCardInfo', async () => {
    const cardBody = agentCardResponse();
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(cardBody));

    const card = await discoverAgent('http://test-agent:8787');

    expect(fetch).toHaveBeenCalledOnce();
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toBe('http://test-agent:8787/.well-known/agent-card.json');

    expect(card.name).toBe('TestAgent');
    expect(card.description).toBe('A test agent');
    expect(card.version).toBe('1.2.0');
    expect(card.url).toBe('http://test-agent:8787');
    expect(card.supportsStreaming).toBe(true);
    expect(card.supportsPush).toBe(false);
    expect(card.skills).toHaveLength(2);
    expect(card.skills[0]).toEqual({ id: 'greet', name: 'greet', description: 'Says hello' });
    expect(card.raw).toBeDefined();
  });

  it('strips trailing slash from agentUrl', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(agentCardResponse()));

    await discoverAgent('http://test-agent:8787/');

    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toBe('http://test-agent:8787/.well-known/agent-card.json');
  });

  it('throws RemoteAgentError on non-ok response', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse({}, 404));

    await expect(discoverAgent('http://agent')).rejects.toThrow(RemoteAgentError);
  });

  it('rejects A2A 0.3 cards with a clear error', async () => {
    const legacyCard = {
      name: 'LegacyAgent',
      protocolVersion: '0.3.0',
      url: 'http://legacy:8787/a2a/jsonrpc',
      skills: [],
    };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(legacyCard));

    await expect(discoverAgent('http://legacy:8787')).rejects.toThrow(
      'speaks A2A 0.3, not supported by a2a-lite 1.0'
    );
  });

  it('returns correct shape (AgentCardInfo)', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(agentCardResponse()));

    const card: AgentCardInfo = await discoverAgent('http://agent');

    // Verify the shape has all required properties
    expect(card).toHaveProperty('name');
    expect(card).toHaveProperty('description');
    expect(card).toHaveProperty('url');
    expect(card).toHaveProperty('version');
    expect(card).toHaveProperty('skills');
    expect(card).toHaveProperty('supportsStreaming');
    expect(card).toHaveProperty('supportsPush');
    expect(card).toHaveProperty('raw');
  });
});

// ---------------------------------------------------------------------------
// AgentNetwork.add() with autoDiscover
// ---------------------------------------------------------------------------

describe('AgentNetwork.add() with autoDiscover', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('triggers discovery when autoDiscover is true', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(agentCardResponse()));

    const net = new AgentNetwork();
    net.add('test', 'http://test-agent:8787', { autoDiscover: true });

    // Give the fire-and-forget discovery a tick to complete
    await new Promise((r) => setTimeout(r, 50));

    expect(fetch).toHaveBeenCalledOnce();
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string];
    expect(url).toBe('http://test-agent:8787/.well-known/agent-card.json');

    const card = net.getCard('test');
    expect(card).toBeDefined();
    expect(card!.name).toBe('TestAgent');
  });

  it('does not trigger discovery when autoDiscover is not set', () => {
    const net = new AgentNetwork();
    net.add('test', 'http://test-agent:8787');

    expect(fetch).not.toHaveBeenCalled();
    expect(net.getCard('test')).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// AgentNetwork.discover() and getCard()
// ---------------------------------------------------------------------------

describe('AgentNetwork.discover()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('fetches and caches the agent card', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(agentCardResponse()));

    const net = new AgentNetwork({ bot: 'http://bot:3000' });
    const card = await net.discover('bot');

    expect(card.name).toBe('TestAgent');
    expect(net.getCard('bot')).toBe(card);
  });

  it('throws for unknown agent name', async () => {
    const net = new AgentNetwork();
    await expect(net.discover('nope')).rejects.toThrow("Agent 'nope' not found");
  });
});

// ---------------------------------------------------------------------------
// Agent.delegate() with returnHandle and discover
// ---------------------------------------------------------------------------

describe('Agent.delegate() with options', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('delegate with returnHandle returns a TaskHandle', async () => {
    // We test via AgentNetwork.call since Agent.delegate uses it under the hood
    // when a network name is used with returnHandle
    const body = a2aResponse('"result"', 'task-delegate');
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const net = new AgentNetwork({ weather: 'http://weather:8788' });
    const handle = await net.call('weather', 'forecast', { city: 'NYC' }, 30000, { returnHandle: true });

    expect(handle).toBeInstanceOf(TaskHandle);
    expect((handle as TaskHandle).taskId).toBe('task-delegate');
  });

  it('delegate with discover validates skill exists', async () => {
    // Import Agent class
    const { Agent } = await import('../src/agent.js');
    const { AgentNetwork: AN } = await import('../src/orchestration.js');

    const net = new AN({ data: 'http://data:8787' });
    const agent = new Agent({
      name: 'Test',
      description: 'Test agent',
      network: net,
    });

    // Mock fetch to return agent card for discovery, then fail for non-existent skill
    const cardBody = agentCardResponse(); // has 'greet' and 'calc' skills
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(cardBody));

    await expect(
      agent.delegate('data', 'nonexistent', {}, { discover: true })
    ).rejects.toThrow("Skill 'nonexistent' not found on agent");
  });

  it('delegate with discover succeeds for valid skill', async () => {
    const { Agent } = await import('../src/agent.js');
    const { AgentNetwork: AN } = await import('../src/orchestration.js');

    const net = new AN({ data: 'http://data:8787' });
    const agent = new Agent({
      name: 'Test',
      description: 'Test agent',
      network: net,
    });

    // First call returns agent card (for discovery), second returns A2A response
    const cardBody = agentCardResponse();
    const a2aBody = a2aResponse('"hello"', 'task-disc');
    (fetch as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce(mockJsonResponse(cardBody))
      .mockResolvedValueOnce(mockJsonResponse(a2aBody));

    const result = await agent.delegate('data', 'greet', { name: 'World' }, { discover: true });
    expect(result).toBe('hello');
  });
});

// ---------------------------------------------------------------------------
// AgentNetwork.getTask() and AgentNetwork.cancelTask()
// ---------------------------------------------------------------------------

describe('AgentNetwork.getTask()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('resolves agent URL from name and sends GetTask', async () => {
    const body = { jsonrpc: '2.0', id: '1', result: { id: 'task-1', status: { state: 'TASK_STATE_COMPLETED' } } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const net = new AgentNetwork({ bot: 'http://bot:3000' });
    const result = await net.getTask('bot', 'task-1');

    expect(result).toEqual({ id: 'task-1', status: { state: 'TASK_STATE_COMPLETED' } });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://bot:3000');
    const reqBody = JSON.parse(init.body as string);
    expect(reqBody.method).toBe('GetTask');
    expect(reqBody.params.id).toBe('task-1');
  });

  it('throws for unknown agent name', async () => {
    const net = new AgentNetwork();
    await expect(net.getTask('nope', 'task-1')).rejects.toThrow("Agent 'nope' not found in network.");
  });
});

describe('AgentNetwork.cancelTask()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('resolves agent URL from name and sends CancelTask', async () => {
    const body = { jsonrpc: '2.0', id: '1', result: { id: 'task-1', status: { state: 'TASK_STATE_CANCELED' } } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(body));

    const net = new AgentNetwork({ bot: 'http://bot:3000' });
    const result = await net.cancelTask('bot', 'task-1');

    expect(result).toEqual({ id: 'task-1', status: { state: 'TASK_STATE_CANCELED' } });

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://bot:3000');
    const reqBody = JSON.parse(init.body as string);
    expect(reqBody.method).toBe('CancelTask');
    expect(reqBody.params.id).toBe('task-1');
  });

  it('throws for unknown agent name', async () => {
    const net = new AgentNetwork();
    await expect(net.cancelTask('nope', 'task-1')).rejects.toThrow("Agent 'nope' not found in network.");
  });
});
