import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AgentNetwork, callRemoteSkill } from '../src/orchestration.js';
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

// ---------------------------------------------------------------------------
// AgentNetwork — construction & CRUD
// ---------------------------------------------------------------------------

describe('AgentNetwork', () => {
  it('initializes empty when no agents provided', () => {
    const net = new AgentNetwork();
    expect(net.size).toBe(0);
    expect(net.list()).toEqual({});
  });

  it('initializes with agents from constructor', () => {
    const net = new AgentNetwork({ alpha: 'http://a:3000', beta: 'http://b:3000' });
    expect(net.size).toBe(2);
    expect(net.get('alpha')).toBe('http://a:3000');
  });

  it('strips trailing slashes from URLs', () => {
    const net = new AgentNetwork({ a: 'http://a:3000/' });
    expect(net.get('a')).toBe('http://a:3000');
  });

  it('add() registers a new agent', () => {
    const net = new AgentNetwork();
    net.add('gamma', 'http://g:3000/');
    expect(net.get('gamma')).toBe('http://g:3000');
    expect(net.size).toBe(1);
  });

  it('remove() deletes an agent', () => {
    const net = new AgentNetwork({ x: 'http://x' });
    expect(net.remove('x')).toBe(true);
    expect(net.size).toBe(0);
  });

  it('remove() returns false for unknown agent', () => {
    const net = new AgentNetwork();
    expect(net.remove('nope')).toBe(false);
  });

  it('list() returns all agents as a plain object', () => {
    const net = new AgentNetwork({ a: 'http://a', b: 'http://b' });
    expect(net.list()).toEqual({ a: 'http://a', b: 'http://b' });
  });
});

// ---------------------------------------------------------------------------
// AgentNetwork.call()
// ---------------------------------------------------------------------------

describe('AgentNetwork.call()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('throws when agent name is not in network', async () => {
    const net = new AgentNetwork();
    await expect(net.call('unknown', 'ping')).rejects.toThrow("Agent 'unknown' not found");
  });

  it('calls fetch with the correct URL', async () => {
    const responseBody = { result: { parts: [{ kind: 'text', text: '"pong"' }] } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    const net = new AgentNetwork({ bot: 'http://bot:3000' });
    const result = await net.call('bot', 'ping');

    expect(fetch).toHaveBeenCalledOnce();
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://bot:3000');
    expect(result).toBe('pong');
  });
});

// ---------------------------------------------------------------------------
// AgentNetwork.broadcast()
// ---------------------------------------------------------------------------

describe('AgentNetwork.broadcast()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('calls all agents and collects results', async () => {
    const responseBody = { result: { parts: [{ kind: 'text', text: '"ok"' }] } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    const net = new AgentNetwork({ a: 'http://a', b: 'http://b' });
    const results = await net.broadcast('health');

    expect(results.a).toBe('ok');
    expect(results.b).toBe('ok');
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('captures errors per-agent without throwing', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('network down'));

    const net = new AgentNetwork({ a: 'http://a' });
    const results = await net.broadcast('health');

    expect(results.a).toHaveProperty('error');
  });
});

// ---------------------------------------------------------------------------
// callRemoteSkill()
// ---------------------------------------------------------------------------

describe('callRemoteSkill()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends a JSON-RPC request with skill and params', async () => {
    const responseBody = { result: { parts: [{ kind: 'text', text: '"done"' }] } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    await callRemoteSkill('http://agent', 'doWork', { x: 1 });

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.jsonrpc).toBe('2.0');
    expect(body.method).toBe('message/send');
    expect(body.params.message.role).toBe('user');
  });

  it('throws RemoteAgentError on non-ok HTTP response', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse({}, 500));

    await expect(callRemoteSkill('http://agent', 'fail', {})).rejects.toThrow(RemoteAgentError);
  });

  it('throws RemoteAgentError when response contains an error field', async () => {
    const errorResponse = { error: 'skill not found' };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(errorResponse));

    await expect(callRemoteSkill('http://agent', 'missing', {})).rejects.toThrow(RemoteAgentError);
  });

  it('parses JSON text parts from the response', async () => {
    const responseBody = { result: { parts: [{ kind: 'text', text: '{"answer":42}' }] } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    const result = await callRemoteSkill('http://agent', 'calc', {});
    expect(result).toEqual({ answer: 42 });
  });

  it('returns raw text when JSON parsing fails', async () => {
    const responseBody = { result: { parts: [{ kind: 'text', text: 'just a string' }] } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    const result = await callRemoteSkill('http://agent', 'echo', {});
    expect(result).toBe('just a string');
  });

  it('falls back to result object when no text parts exist', async () => {
    const responseBody = { result: { custom: 'data' } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    const result = await callRemoteSkill('http://agent', 'raw', {});
    expect(result).toEqual({ custom: 'data' });
  });

  it('also handles type: "text" parts (not just kind: "text")', async () => {
    const responseBody = { result: { parts: [{ type: 'text', text: '"hello"' }] } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    const result = await callRemoteSkill('http://agent', 'greet', {});
    expect(result).toBe('hello');
  });
});
