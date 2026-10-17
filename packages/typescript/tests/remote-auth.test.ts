import { afterEach, describe, expect, it, vi } from 'vitest';
import { AgentNetwork, callRemoteSkillWithHandle, streamRemoteSkill } from '../src/orchestration.js';

const task = { result: { task: { id: 'real-task', status: { message: { parts: [{ text: 'done' }] } } } } };
const card = (url: string) => ({
  name: 'Peer',
  description: 'Test',
  version: '1',
  skills: [],
  capabilities: {},
  supportedInterfaces: [{ url, protocolBinding: 'JSONRPC', protocolVersion: '1.0' }],
});

afterEach(() => vi.unstubAllGlobals());
describe('scoped rotating client credentials', () => {
  it('refreshes credentials on calls and every task operation while preserving tenant', async () => {
    const fetcher = vi.fn().mockImplementation(async () => Response.json(task));
    vi.stubGlobal('fetch', fetcher);
    let token = 'first';
    const handle = await callRemoteSkillWithHandle('https://peer.example/rpc', 'work', {}, 1000, {
      tenant: 'team',
      credentialProvider: () => ({ Authorization: `Bearer ${token}` }),
    });
    token = 'rotated';
    await handle.getStatus();
    await handle.cancel();
    await handle.subscribe('https://callback.example');
    await handle.getPushConfig();
    await handle.unsubscribe();
    expect(fetcher).toHaveBeenCalledTimes(6);
    for (const [index, [, options]] of fetcher.mock.calls.entries()) {
      expect(options.headers.authorization).toBe(`Bearer ${index === 0 ? 'first' : 'rotated'}`);
      expect(JSON.parse(options.body).params.tenant).toBe('team');
      expect(options.redirect).toBe('error');
    }
  });
  it('does not invoke a credential provider for a discovery-advertised foreign origin', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json(card('https://other.example/rpc')));
    vi.stubGlobal('fetch', fetcher);
    const provider = vi.fn(() => ({ Authorization: 'Bearer private' }));
    const network = new AgentNetwork({ peer: 'https://peer.example' }).withCredentials('peer', {
      credentialProvider: provider,
    });
    await network.discover('peer');
    await expect(network.call('peer', 'work')).rejects.toThrow('credential origin');
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(provider).toHaveBeenCalledTimes(1);
  });
  it('permits an explicitly configured credential origin and propagates stream credentials', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(Response.json(card('https://other.example/rpc')))
      .mockResolvedValueOnce(Response.json(task));
    vi.stubGlobal('fetch', fetcher);
    const network = new AgentNetwork({ peer: 'https://peer.example' }).withCredentials('peer', {
      headers: { Authorization: 'Bearer secret' },
      allowedCredentialOrigins: ['https://other.example'],
    });
    await network.discover('peer');
    await network.call('peer', 'work');
    expect(fetcher.mock.calls[1][0]).toBe('https://other.example/rpc');
    expect(fetcher.mock.calls[1][1].headers.authorization).toBe('Bearer secret');
    fetcher.mockResolvedValueOnce(new Response('data: {"result":{"message":{"parts":[{"text":"done"}]}}}\n\n'));
    const values = [];
    for await (const value of streamRemoteSkill('https://peer.example', 'work', {}, 1000, {
      headers: { Authorization: 'Bearer rotated' },
    }))
      values.push(value);
    expect(values).toEqual(['done']);
    expect(fetcher.mock.calls[2][1].headers.authorization).toBe('Bearer rotated');
  });
});
