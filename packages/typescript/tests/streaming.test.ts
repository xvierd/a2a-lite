import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { AgentNetwork, streamRemoteSkill } from '../src/orchestration.js';
import { Agent } from '../src/agent.js';
import { RemoteAgentError } from '../src/errors.js';

// ---------------------------------------------------------------------------
// Helpers — mock SSE Response with a ReadableStream body
// ---------------------------------------------------------------------------

function mockSSEResponse(sseData: string, status = 200): Response {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode(sseData));
      controller.close();
    },
  });

  return new Response(stream, {
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

function mockSSEResponseChunked(chunks: string[], status = 200): Response {
  const encoder = new TextEncoder();
  let index = 0;
  const stream = new ReadableStream({
    pull(controller) {
      if (index < chunks.length) {
        controller.enqueue(encoder.encode(chunks[index]));
        index++;
      } else {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

// ---------------------------------------------------------------------------
// streamRemoteSkill()
// ---------------------------------------------------------------------------

describe('streamRemoteSkill()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('yields text chunks from artifact parts and stops at final', async () => {
    const sseData = [
      'data: {"artifact":{"parts":[{"kind":"text","text":"Hello"}]},"final":false}\n\n',
      'data: {"artifact":{"parts":[{"kind":"text","text":" World"}]},"final":false}\n\n',
      'data: {"status":{"state":"completed"},"final":true}\n\n',
    ].join('');

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponse(sseData));

    const chunks: string[] = [];
    for await (const chunk of streamRemoteSkill('http://agent', 'echo', {})) {
      chunks.push(chunk);
    }

    expect(chunks).toEqual(['Hello', ' World']);
  });

  it('handles type: "text" parts (not just kind: "text")', async () => {
    const sseData = [
      'data: {"artifact":{"parts":[{"type":"text","text":"typed"}]},"final":false}\n\n',
      'data: {"status":{"state":"completed"},"final":true}\n\n',
    ].join('');

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponse(sseData));

    const chunks: string[] = [];
    for await (const chunk of streamRemoteSkill('http://agent', 'echo', {})) {
      chunks.push(chunk);
    }

    expect(chunks).toEqual(['typed']);
  });

  it('throws RemoteAgentError on failed status', async () => {
    const sseData =
      'data: {"status":{"state":"failed","message":{"parts":[{"text":"something broke"}]}},"final":true}\n\n';

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponse(sseData));

    const chunks: string[] = [];
    await expect(async () => {
      for await (const chunk of streamRemoteSkill('http://agent', 'fail', {})) {
        chunks.push(chunk);
      }
    }).rejects.toThrow(RemoteAgentError);
  });

  it('throws RemoteAgentError on non-ok HTTP response', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('Internal Server Error', { status: 500 }),
    );

    await expect(async () => {
      for await (const _chunk of streamRemoteSkill('http://agent', 'fail', {})) {
        // should not reach here
      }
    }).rejects.toThrow(RemoteAgentError);
  });

  it('sends a JSON-RPC request with method message/stream', async () => {
    const sseData = 'data: {"status":{"state":"completed"},"final":true}\n\n';
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponse(sseData));

    const chunks: string[] = [];
    for await (const chunk of streamRemoteSkill('http://agent', 'doWork', { x: 1 })) {
      chunks.push(chunk);
    }

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.jsonrpc).toBe('2.0');
    expect(body.method).toBe('message/stream');
    expect(body.params.message.role).toBe('user');
  });

  it('handles chunked delivery across multiple reads', async () => {
    const chunks = [
      'data: {"artifact":{"parts":[{"kind":"text","text":"ch',
      'unk1"}]},"final":false}\n\ndata: {"artifact":{"parts":[{"kind":"text","text":"chunk2"}]},"final":false}\n\n',
      'data: {"status":{"state":"completed"},"final":true}\n\n',
    ];

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponseChunked(chunks));

    const result: string[] = [];
    for await (const chunk of streamRemoteSkill('http://agent', 'echo', {})) {
      result.push(chunk);
    }

    expect(result).toEqual(['chunk1', 'chunk2']);
  });

  it('stops at canceled state', async () => {
    const sseData = [
      'data: {"artifact":{"parts":[{"kind":"text","text":"partial"}]},"final":false}\n\n',
      'data: {"status":{"state":"canceled"},"final":true}\n\n',
    ].join('');

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponse(sseData));

    const result: string[] = [];
    for await (const chunk of streamRemoteSkill('http://agent', 'echo', {})) {
      result.push(chunk);
    }

    expect(result).toEqual(['partial']);
  });

  it('ignores non-data SSE lines', async () => {
    const sseData = [
      ':comment line\n',
      'event: update\n',
      'data: {"artifact":{"parts":[{"kind":"text","text":"ok"}]},"final":false}\n\n',
      'data: {"status":{"state":"completed"},"final":true}\n\n',
    ].join('');

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponse(sseData));

    const result: string[] = [];
    for await (const chunk of streamRemoteSkill('http://agent', 'echo', {})) {
      result.push(chunk);
    }

    expect(result).toEqual(['ok']);
  });
});

// ---------------------------------------------------------------------------
// AgentNetwork.stream()
// ---------------------------------------------------------------------------

describe('AgentNetwork.stream()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('throws when agent name is not in network', async () => {
    const net = new AgentNetwork();
    await expect(async () => {
      for await (const _chunk of net.stream('unknown', 'echo')) {
        // should not reach here
      }
    }).rejects.toThrow("Agent 'unknown' not found");
  });

  it('yields text chunks from the named agent', async () => {
    const sseData = [
      'data: {"artifact":{"parts":[{"kind":"text","text":"A"}]},"final":false}\n\n',
      'data: {"artifact":{"parts":[{"kind":"text","text":"B"}]},"final":false}\n\n',
      'data: {"status":{"state":"completed"},"final":true}\n\n',
    ].join('');

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponse(sseData));

    const net = new AgentNetwork({ bot: 'http://bot:3000' });
    const chunks: string[] = [];
    for await (const chunk of net.stream('bot', 'echo')) {
      chunks.push(chunk);
    }

    expect(chunks).toEqual(['A', 'B']);
    const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://bot:3000');
  });
});

// ---------------------------------------------------------------------------
// Agent.delegate() with stream: true
// ---------------------------------------------------------------------------

describe('Agent.delegate() with stream: true', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('returns an async generator when stream: true', async () => {
    const sseData = [
      'data: {"artifact":{"parts":[{"kind":"text","text":"Hello"}]},"final":false}\n\n',
      'data: {"artifact":{"parts":[{"kind":"text","text":" World"}]},"final":false}\n\n',
      'data: {"status":{"state":"completed"},"final":true}\n\n',
    ].join('');

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponse(sseData));

    const network = new AgentNetwork({ story: 'http://story:8787' });
    const agent = new Agent({ name: 'Test', description: 'Test agent', network });

    const gen = await agent.delegate('story', 'tellStory', { topic: 'cats' }, { stream: true });

    const chunks: string[] = [];
    for await (const chunk of gen as AsyncGenerator<string>) {
      chunks.push(chunk);
    }

    expect(chunks).toEqual(['Hello', ' World']);
  });

  it('works with direct URL and stream: true', async () => {
    const sseData = [
      'data: {"artifact":{"parts":[{"kind":"text","text":"direct"}]},"final":false}\n\n',
      'data: {"status":{"state":"completed"},"final":true}\n\n',
    ].join('');

    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockSSEResponse(sseData));

    const agent = new Agent({ name: 'Test', description: 'Test agent' });

    const gen = await agent.delegate('http://remote:8787', 'skill', {}, { stream: true });

    const chunks: string[] = [];
    for await (const chunk of gen as AsyncGenerator<string>) {
      chunks.push(chunk);
    }

    expect(chunks).toEqual(['direct']);
  });
});
