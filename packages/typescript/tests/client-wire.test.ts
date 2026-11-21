import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  Agent,
  AgentNetwork,
  callRemoteSkill,
  callRemoteSkillResult,
  getRemoteTask,
  streamRemoteSkill,
  streamRemoteSkillEvents,
  subscribeToTask,
} from '../src/index.js';
import { rpcReply, sseReply } from './rpc-peer.js';

const base = 'https://peer.example/bots/shop';
const endpoint = 'https://peer.example/a2a/rpc';
const error = { code: -32602, message: 'Invalid task', data: { taskId: 't' } };
const working = {
  statusUpdate: { taskId: 't', status: { state: 'TASK_STATE_WORKING', message: { parts: [{ text: 'first' }] } } },
};
const artifact = {
  artifactUpdate: {
    taskId: 't',
    append: true,
    artifact: {
      artifactId: 'a',
      metadata: { kind: 'photo' },
      parts: [{ raw: 'AQI=', mediaType: 'image/png', metadata: { alt: 'tile' } }],
    },
  },
};
const frame = (result: unknown) => 'data: ' + JSON.stringify({ jsonrpc: '2.0', id: '$id', result }) + '\n\n';
const snapshot = (id: string, state = 'TASK_STATE_WORKING') => ({ task: { id, status: { state } } });
const completed = { statusUpdate: { taskId: 't', status: { state: 'TASK_STATE_COMPLETED' } } };
const card = {
  supportedInterfaces: [
    { url: 'https://peer.example/rest', protocolBinding: 'HTTP+JSON', protocolVersion: '1.0', tenant: 'rest' },
    { url: endpoint, protocolBinding: 'JSONRPC', protocolVersion: '1.0', tenant: 'blue' },
  ],
  skills: [{ id: 'work' }],
};

afterEach(() => vi.unstubAllGlobals());

describe('correlated JSON-RPC envelopes', () => {
  const operations = {
    message: () => callRemoteSkill(base, 'work', {}),
    task: () => getRemoteTask(base, 't'),
    stream: () => streamRemoteSkill(base, 'work').next(),
  };
  for (const [name, invoke] of Object.entries(operations)) {
    it.each([
      ['version', { jsonrpc: '1.0', result: {} }, /version/i],
      ['ID', { id: 0, result: {} }, /ID mismatch/],
      ['missing result and error', {}, /exactly one/],
      ['both result and error', { result: {}, error }, /exactly one/],
      ['malformed error', { error: { message: 'no code' } }, /error object/],
    ] as const)(name + ' rejects %s', async (_label, overrides, reason) => {
      vi.stubGlobal('fetch', async (_url: string, init: RequestInit) => {
        const { id } = JSON.parse(String(init.body));
        const body = { jsonrpc: '2.0', id, ...overrides };
        return name === 'stream'
          ? new Response('data: ' + JSON.stringify(body) + '\n\n', { headers: { 'content-type': 'text/event-stream' } })
          : Response.json(body);
      });
      await expect(invoke()).rejects.toThrow(reason);
    });
  }
  it.each([200, 400])('preserves a JSON error before the SSE stream opens (HTTP %i)', async (status) => {
    vi.stubGlobal('fetch', rpcReply({ error }, status));
    await expect(streamRemoteSkill(base, 'work').next()).rejects.toMatchObject({ name: 'RemoteAgentError', ...error });
  });
  it('returns code and data on a unary error', async () => {
    vi.stubGlobal('fetch', rpcReply({ error }));
    await expect(getRemoteTask(base, 't')).rejects.toMatchObject(error);
  });
});

describe('SSE wire framing', () => {
  it.each(['\r', '\n', '\r\n'])('decodes UTF-8 and multiple data fields with %j line endings', async (eol) => {
    vi.stubGlobal('fetch', async (_url: string, init: RequestInit) => {
      const { id } = JSON.parse(String(init.body));
      const lines = [
        ': keepalive',
        'event: message',
        `data: {"jsonrpc":"2.0","id":${JSON.stringify(id)},`,
        'data: "result":{"message":{"parts":[{"text":"café 🍉"}]}}}',
        '',
        '',
      ];
      const bytes = new TextEncoder().encode(lines.join(eol));
      let offset = 0;
      const body = new ReadableStream({
        pull(c) {
          if (offset === bytes.length) c.close();
          else c.enqueue(bytes.subarray(offset, ++offset));
        },
      });
      return new Response(body, { headers: { 'content-type': 'Text/Event-Stream; charset=utf-8' } });
    });
    const iter = streamRemoteSkill(base, 'work');
    expect(await iter.next()).toEqual({ done: false, value: 'café 🍉' });
    expect((await iter.next()).done).toBe(true);
  });
  it('yields a chunk once, then throws the correlated error with details', async () => {
    vi.stubGlobal(
      'fetch',
      sseReply(frame(working) + 'event: error\ndata: ' + JSON.stringify({ jsonrpc: '2.0', id: '$id', error }) + '\n\n'),
    );
    const iterator = streamRemoteSkill(base, 'work');
    expect(await iterator.next()).toEqual({ value: 'first', done: false });
    await expect(iterator.next()).rejects.toMatchObject(error);
    expect((await iterator.next()).done).toBe(true);
  });
  it.each([
    ['', /final message or task state/],
    ['data: {}\n', /end of an event/],
    ['data: {\n\n', /Invalid JSON/],
  ])('reports premature EOF or malformed frame %j after a delivered chunk', async (tail, reason) => {
    vi.stubGlobal('fetch', sseReply(frame(working) + tail));
    const iterator = streamRemoteSkill(base, 'work');
    expect((await iterator.next()).value).toBe('first');
    await expect(iterator.next()).rejects.toThrow(reason);
  });
  it('cancels the reader when a consumer leaves an active stream', async () => {
    const cancel = vi.fn();
    let body: ReadableStream<Uint8Array>;
    vi.stubGlobal('fetch', async (_url: string, init: RequestInit) => {
      body = new ReadableStream({
        start(c) {
          c.enqueue(new TextEncoder().encode(frame(working).replace('$id', JSON.parse(String(init.body)).id)));
        },
        cancel,
      });
      return new Response(body, { headers: { 'content-type': 'text/event-stream' } });
    });
    for await (const value of streamRemoteSkill(base, 'work')) {
      expect(value).toBe('first');
      break;
    }
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(body!.locked).toBe(false);
  });
  it.each(['TASK_STATE_INPUT_REQUIRED', 'TASK_STATE_AUTH_REQUIRED'])(
    'follows a live subscription after %s and releases it on completion even when the peer stays connected',
    async (state) => {
      const paused = { statusUpdate: { taskId: 't', status: { state } } };
      const cancel = vi.fn();
      vi.stubGlobal('fetch', async (_url: string, init: RequestInit) => {
        const { id, method } = JSON.parse(String(init.body));
        expect(method).toBe('SubscribeToTask');
        const frames = [snapshot('t'), paused, working, completed].map(frame).join('').replaceAll('$id', id);
        return new Response(
          new ReadableStream({
            start(controller) {
              controller.enqueue(new TextEncoder().encode(frames));
            },
            cancel,
          }),
          { headers: { 'content-type': 'text/event-stream' } },
        );
      });
      const states = [];
      for await (const event of subscribeToTask(base, 't')) states.push(event.raw);
      expect(states).toEqual([snapshot('t'), paused, working, completed]);
      expect(cancel).toHaveBeenCalledOnce();
      vi.stubGlobal('fetch', sseReply(frame(snapshot('t', state))));
      const iterator = subscribeToTask(base, 't');
      await iterator.next();
      expect((await iterator.next()).done).toBe(true);
    },
  );
  it.each([
    [{ message: { taskId: 't', parts: [] } }, /snapshot/],
    [working, /snapshot/],
    [artifact, /snapshot/],
    [snapshot('wrong'), /task ID mismatch/],
  ])('rejects an invalid initial subscription event %j', async (result, error) => {
    vi.stubGlobal('fetch', sseReply(frame(result)));
    await expect(subscribeToTask(base, 't').next()).rejects.toThrow(error);
  });
  it.each([
    snapshot('wrong'),
    { statusUpdate: { ...completed.statusUpdate, taskId: 'wrong' } },
    { artifactUpdate: { ...artifact.artifactUpdate, taskId: 'wrong' } },
  ])('rejects a subscription event for another task after its snapshot', async (result) => {
    vi.stubGlobal('fetch', sseReply(frame(snapshot('t')) + frame(result)));
    const iterator = subscribeToTask(base, 't');
    expect((await iterator.next()).value?.$case).toBe('task');
    await expect(iterator.next()).rejects.toThrow('task ID mismatch');
  });
  it('preserves a subscription RPC error before any snapshot', async () => {
    vi.stubGlobal('fetch', rpcReply({ error }));
    await expect(subscribeToTask(base, 't').next()).rejects.toMatchObject(error);
  });
  it('releases a Message-only stream as soon as its single response is delivered', async () => {
    const cancel = vi.fn();
    vi.stubGlobal('fetch', async (_url: string, init: RequestInit) => {
      const data = frame({ message: { parts: [{ text: 'done' }] } }).replace('$id', JSON.parse(String(init.body)).id);
      return new Response(
        new ReadableStream({
          start(c) {
            c.enqueue(new TextEncoder().encode(data));
          },
          cancel,
        }),
        { headers: { 'content-type': 'text/event-stream' } },
      );
    });
    const iterator = streamRemoteSkill(base, 'work');
    expect((await iterator.next()).value).toBe('done');
    expect((await iterator.next()).done).toBe(true);
    expect(cancel).toHaveBeenCalledOnce();
  });
  it('keeps typed part content, artifact metadata and wire presence of lastChunk', async () => {
    vi.stubGlobal('fetch', sseReply(frame(artifact) + frame(completed)));
    const events = [];
    for await (const event of streamRemoteSkillEvents(base, 'work')) events.push(event);
    expect(events.map((e) => e.$case)).toEqual(['artifactUpdate', 'statusUpdate']);
    expect(events[0].raw).toEqual(artifact);
    expect(events[0].value).toMatchObject({
      append: true,
      artifact: {
        metadata: { kind: 'photo' },
        parts: [{ content: { $case: 'raw', value: Buffer.from([1, 2]) }, metadata: { alt: 'tile' } }],
      },
    });
  });
  it('exposes a complete non-streaming Message', async () => {
    const message = { messageId: 'reply', metadata: { locale: 'es' }, parts: [{ text: 'Hola' }, { data: { n: 2 } }] };
    vi.stubGlobal('fetch', rpcReply({ result: { message } }));
    expect(await callRemoteSkillResult(base, 'work')).toMatchObject({
      $case: 'message',
      raw: { message },
      value: {
        messageId: 'reply',
        metadata: { locale: 'es' },
        parts: [{ content: { $case: 'text', value: 'Hola' } }, { content: { $case: 'data', value: { n: 2 } } }],
      },
    });
  });
});

describe('selected endpoint and credentials', () => {
  it('rediscovers from the registration and uses its tenant for calls, task operations, subscription and push', async () => {
    let token = 'old';
    const requests: Array<{ url: string; method: string; tenant?: string; key: string | null }> = [];
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      const key = new Headers(init.headers).get('x-api-key');
      if (init.method === 'GET') {
        requests.push({ url, method: 'GET', key });
        return Response.json(card);
      }
      const { method, params } = JSON.parse(String(init.body));
      requests.push({ url, method, tenant: params.tenant, key });
      if (method === 'SubscribeToTask') return sseReply(frame(snapshot(params.id, 'TASK_STATE_COMPLETED')))(url, init);
      if (method === 'SendStreamingMessage') return sseReply(frame(completed))(url, init);
      return rpcReply({ result: method === 'SendMessage' ? { task: { id: 'remote' } } : {} })(url, init);
    });
    const network = new AgentNetwork({ shop: base }).withCredentials('shop', {
      credentialProvider: () => ({ 'X-API-Key': token }),
    });
    expect((await network.discover('shop')).tenant).toBe('blue');
    const agent = new Agent({ name: 'Buyer', description: 'Delegate', network });
    const handle = await agent.delegate('shop', 'work', {}, { discover: true, returnHandle: true });
    token = 'new';
    await handle.get();
    await handle.cancel();
    await handle.subscribe('https://callback.example');
    await handle.getPushConfig();
    await handle.unsubscribe();
    for await (const event of handle.streamEvents()) expect(event.$case).toBe('task');
    for await (const event of network.streamEvents('shop', 'work')) expect(event.$case).toBe('statusUpdate');
    await network.listTasks('shop');
    await network.broadcast('work');
    expect(requests.map((r) => r.method)).toEqual([
      'GET',
      'GET',
      'SendMessage',
      'GetTask',
      'CancelTask',
      'CreateTaskPushNotificationConfig',
      'GetTaskPushNotificationConfig',
      'DeleteTaskPushNotificationConfig',
      'SubscribeToTask',
      'SendStreamingMessage',
      'ListTasks',
      'SendMessage',
    ]);
    expect(requests.slice(0, 2).every((r) => r.url === base + '/.well-known/agent-card.json')).toBe(true);
    expect(requests.slice(2).every((r) => r.url === endpoint && r.tenant === 'blue')).toBe(true);
    expect(requests.slice(3).every((r) => r.key === 'new')).toBe(true);
  });
  it('selects the corresponding cached interface for two concurrent tenants and rejects an unavailable tenant', async () => {
    const peerCard = {
      ...card,
      supportedInterfaces: [
        ...card.supportedInterfaces,
        { url: endpoint + '/green', protocolBinding: 'JSONRPC', protocolVersion: '1.0.1', tenant: 'green' },
      ],
    };
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      if (init.method === 'GET') return Response.json(peerCard);
      const { params } = JSON.parse(String(init.body));
      return rpcReply({ result: { message: { parts: [{ text: params.tenant + ':' + url }] } } })(url, init);
    });
    vi.stubGlobal('fetch', fetcher);
    const network = new AgentNetwork({ peer: base });
    await network.discover('peer');
    expect(
      await Promise.all(['blue', 'green'].map((tenant) => network.call('peer', 'work', {}, 1000, { tenant }))),
    ).toEqual(['blue:' + endpoint, 'green:' + endpoint + '/green']);
    await expect(network.call('peer', 'work', {}, 1000, { tenant: 'other' })).rejects.toThrow('tenant');
    expect(fetcher).toHaveBeenCalledTimes(3);
    expect(network.getCard('peer')?.tenant).toBe('blue');
  });
  it('omits the tenant on an unscoped shared interface, including delegates, continuation and task handles', async () => {
    const sharedCard = {
      ...card,
      supportedInterfaces: [{ url: endpoint, protocolBinding: 'JSONRPC', protocolVersion: '1.0' }],
    };
    const calls: Array<{ url: string; method: string; params: Record<string, unknown> }> = [];
    vi.stubGlobal('fetch', async (url: string, init: RequestInit) => {
      if (init.method === 'GET') return Response.json(sharedCard);
      const { method, params } = JSON.parse(String(init.body));
      calls.push({ url, method, params });
      if (method === 'SubscribeToTask') return sseReply(frame(snapshot(params.id, 'TASK_STATE_COMPLETED')))(url, init);
      return rpcReply({ result: method === 'SendMessage' ? { task: { id: 't' } } : {} })(url, init);
    });
    const network = new AgentNetwork();
    network.add('peer', base, { tenant: 'blue' });
    await network.discover('peer');
    await Promise.all(
      ['blue', 'green'].map((tenant) => network.call('peer', 'work', {}, 1000, { tenant, taskId: 't' })),
    );
    const agent = new Agent({ name: 'Buyer', description: 'Delegate', network });
    const task = await agent.delegate('peer', 'work', {}, { tenant: 'green', returnHandle: true, discover: true });
    await task.get();
    for await (const event of task.streamEvents()) expect(event.$case).toBe('task');
    await task.subscribe('https://callback.example');
    await agent.delegate(base, 'work', {}, { tenant: 'blue', discover: true });
    expect(calls.map((c) => c.method)).toEqual([
      'SendMessage',
      'SendMessage',
      'SendMessage',
      'GetTask',
      'SubscribeToTask',
      'CreateTaskPushNotificationConfig',
      'SendMessage',
    ]);
    for (const call of calls) {
      expect(call.url).toBe(endpoint);
      expect(call.params).not.toHaveProperty('tenant');
    }
    await agent.delegate(endpoint, 'work', {}, { tenant: 'green' });
    expect(calls.at(-1)?.params.tenant).toBe('green');
  });
  it('waits for auto discovery before posting and blocks a call if discovery fails', async () => {
    let release!: () => void;
    const wait = new Promise<void>((r) => {
      release = r;
    });
    const urls: string[] = [];
    const fetcher = vi.fn(async (url: string, init: RequestInit) => {
      urls.push(url);
      if (init.method === 'GET') {
        await wait;
        return Response.json(card);
      }
      expect(JSON.parse(String(init.body)).params.tenant).toBe('blue');
      return rpcReply({ result: { message: { parts: [{ text: 'ok' }] } } })(url, init);
    });
    vi.stubGlobal('fetch', fetcher);
    const network = new AgentNetwork();
    network.add('peer', base, { autoDiscover: true });
    const pending = network.call('peer', 'work');
    await vi.waitFor(() => expect(urls).toEqual([base + '/.well-known/agent-card.json']));
    release();
    expect(await pending).toBe('ok');
    expect(urls.at(-1)).toBe(endpoint);

    fetcher.mockRejectedValueOnce(new Error('discovery failed'));
    network.add('peer', base, { autoDiscover: true });
    await expect(network.call('peer', 'work')).rejects.toThrow('discovery failed');
    await expect(network.getTask('peer', 't')).rejects.toThrow('discovery failed');
    expect(fetcher).toHaveBeenCalledTimes(3);
  });
  it('keeps a delayed discovery response out of a replacement registration', async () => {
    let respond!: (response: Response) => void;
    const pending = new Promise<Response>((r) => {
      respond = r;
    });
    vi.stubGlobal('fetch', vi.fn().mockReturnValueOnce(pending));
    const network = new AgentNetwork();
    network.add('peer', base, { autoDiscover: true });
    const call = network.call('peer', 'work');
    network.add('peer', 'https://replacement.example');
    respond(Response.json(card));
    await expect(call).rejects.toThrow('registration changed');
    expect(network.get('peer')).toBe('https://replacement.example');
    expect(network.getCard('peer')).toBeUndefined();
  });
  it('binds newly supplied per-call credentials to the original discovery origin', async () => {
    const foreign = {
      ...card,
      supportedInterfaces: [{ url: 'https://other.example/rpc', protocolBinding: 'JSONRPC', protocolVersion: '1.0' }],
    };
    const fetcher = vi.fn().mockResolvedValue(Response.json(foreign));
    vi.stubGlobal('fetch', fetcher);
    const network = new AgentNetwork({ peer: base });
    await network.discover('peer');
    const credentialProvider = vi.fn(() => ({ Authorization: 'private' }));
    await expect(network.call('peer', 'work', {}, 1000, { credentialProvider })).rejects.toThrow('credential origin');
    expect(credentialProvider).not.toHaveBeenCalled();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
