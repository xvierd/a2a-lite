import { EventEmitter } from 'node:events';
import { lookup } from 'node:dns/promises';
import { request as httpsRequest, type RequestOptions } from 'node:https';
import { request as httpRequest } from 'node:http';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { isPublicAddress, postWebhook, resolveWebhookTarget } from '../src/push-delivery.js';

vi.mock('node:dns/promises', () => ({ lookup: vi.fn() }));
vi.mock('node:https', () => ({ request: vi.fn() }));
vi.mock('node:http', () => ({ request: vi.fn() }));

const publicAddress = { address: '93.184.216.34', family: 4 };

function respondWith(statusCode: number) {
  const send = vi.fn((_url: URL, _options: RequestOptions, response: (value: unknown) => void) => {
    const req = new EventEmitter();
    return Object.assign(req, { end: vi.fn(() => response({ statusCode, destroy: vi.fn() })) });
  });
  vi.mocked(httpsRequest).mockImplementation(send as never);
  vi.mocked(httpRequest).mockImplementation(send as never);
  return send;
}

describe('public callback delivery', () => {
  beforeEach(() => {
    vi.mocked(lookup)
      .mockReset()
      .mockResolvedValue([publicAddress] as never);
    vi.mocked(httpsRequest).mockReset();
    vi.mocked(httpRequest).mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it.each([
    '127.0.0.1',
    '0.0.0.0',
    '10.0.0.1',
    '172.16.4.5',
    '192.168.1.1',
    '169.254.169.254',
    '100.64.0.1',
    '192.0.2.1',
    '198.18.0.1',
    '224.0.0.1',
    '240.0.0.1',
    '::',
    '::1',
    '::127.0.0.1',
    '::ffff:127.0.0.1',
    'fc00::1',
    'fe80::1',
    'fec0::1',
    '2001:db8::1',
    '64:ff9b::7f00:1',
    '2002:7f00:1::1',
    'ff02::1',
    'garbage',
  ])('rejects non-public addresses: %s', (address) => {
    expect(isPublicAddress(address)).toBe(false);
  });

  it.each(['93.184.216.34', '2606:4700:4700::1111', '::ffff:93.184.216.34'])(
    'allows public unicast addresses: %s',
    (address) => {
      expect(isPublicAddress(address)).toBe(true);
    },
  );

  it.each(['https://127.1/hook', 'https://2130706433/hook', 'https://0x7f000001/hook', 'https://[::ffff:127.0.0.1]/'])(
    'blocks alternative loopback encodings before any connection: %s',
    async (url) => {
      await expect(postWebhook(url, { body: '{}', headers: {}, timeoutMs: 100 })).rejects.toThrow();
      expect(httpsRequest).not.toHaveBeenCalled();
      expect(lookup).not.toHaveBeenCalled();
    },
  );

  it('rejects mixed public/private DNS answers', async () => {
    vi.mocked(lookup).mockResolvedValue([publicAddress, { address: '10.0.0.1', family: 4 }] as never);
    await expect(postWebhook('https://callback.example/', { body: '{}', headers: {}, timeoutMs: 100 })).rejects.toThrow(
      'public',
    );
    expect(httpsRequest).not.toHaveBeenCalled();
  });

  it('pins the validated address while preserving Host and TLS server name, without using proxy agents', async () => {
    const send = respondWith(204);
    await postWebhook('https://callback.example:8443/hook', {
      body: '{"hello":true}',
      headers: { Authorization: 'Bearer secret' },
      timeoutMs: 100,
    });
    const [url, options] = send.mock.calls[0];
    expect(url.hostname).toBe('callback.example');
    expect(options.headers).toMatchObject({ Host: 'callback.example:8443', Authorization: 'Bearer secret' });
    expect(options.servername).toBe('callback.example');
    expect(options.agent).toBe(false);
    // A second DNS response cannot replace the address selected for this connection.
    vi.mocked(lookup).mockResolvedValue([{ address: '127.0.0.1', family: 4 }] as never);
    const callback = vi.fn();
    options.lookup!('callback.example', {}, callback);
    expect(callback).toHaveBeenCalledWith(null, '93.184.216.34', 4);
    const all = vi.fn();
    options.lookup!('callback.example', { all: true }, all);
    expect(all).toHaveBeenCalledWith(null, [publicAddress]);
    expect(lookup).toHaveBeenCalledOnce();
  });

  it('revalidates DNS at delivery after a registration succeeded', async () => {
    await resolveWebhookTarget('https://callback.example/', AbortSignal.timeout(100));
    vi.mocked(lookup).mockResolvedValue([{ address: '127.0.0.1', family: 4 }] as never);
    await expect(postWebhook('https://callback.example/', { body: '{}', headers: {}, timeoutMs: 100 })).rejects.toThrow(
      'public',
    );
    expect(httpsRequest).not.toHaveBeenCalled();
  });

  it('rejects redirects without following them or forwarding credentials', async () => {
    const send = respondWith(302);
    await expect(
      postWebhook('https://callback.example/', {
        body: '{}',
        headers: { Authorization: 'Bearer secret' },
        timeoutMs: 100,
      }),
    ).rejects.toThrow('HTTP 302');
    expect(send).toHaveBeenCalledOnce();
  });

  it('bounds DNS resolution by the delivery timeout', async () => {
    vi.useFakeTimers();
    vi.mocked(lookup).mockReturnValue(new Promise(() => {}) as never);
    const pending = postWebhook('https://slow.example/', { body: '{}', headers: {}, timeoutMs: 50 });
    const assertion = expect(pending).rejects.toThrow('timed out');
    await vi.advanceTimersByTimeAsync(50);
    await assertion;
    expect(httpsRequest).not.toHaveBeenCalled();
  });
});
