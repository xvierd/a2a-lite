import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createHmac } from 'crypto';
import { LogPushNotifier, WebhookPushNotifier } from '../src/push-notifications.js';
import type { PushEvent } from '../src/push-notifications.js';
import { Agent, InMemoryTaskStore } from '../src/index.js';
import { AgentTestClient } from '../src/testing.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeEvent(overrides: Partial<PushEvent> = {}): PushEvent {
  return {
    skill: 'testSkill',
    result: { answer: 42 },
    status: 'completed',
    timestamp: Date.now() / 1000,
    agent: 'TestAgent',
    ...overrides,
  };
}

function mockOkResponse(status = 200): Response {
  return {
    ok: true,
    status,
    statusText: 'OK',
  } as Response;
}

function mockErrorResponse(status: number): Response {
  return {
    ok: false,
    status,
    statusText: 'Error',
  } as Response;
}

// ---------------------------------------------------------------------------
// LogPushNotifier
// ---------------------------------------------------------------------------

describe('LogPushNotifier', () => {
  it('logs the event to console and does not throw', async () => {
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const notifier = new LogPushNotifier();
    const event = makeEvent();

    await expect(notifier.notify(event)).resolves.toBeUndefined();
    expect(consoleSpy).toHaveBeenCalledOnce();

    consoleSpy.mockRestore();
  });

  it('logs the [A2A Push] prefix', async () => {
    const consoleSpy = vi.spyOn(console, 'log').mockImplementation(() => {});
    const notifier = new LogPushNotifier();

    await notifier.notify(makeEvent());

    expect(consoleSpy.mock.calls[0][0]).toBe('[A2A Push]');
    consoleSpy.mockRestore();
  });

  it('does not throw on unusual payloads', async () => {
    vi.spyOn(console, 'log').mockImplementation(() => {});
    const notifier = new LogPushNotifier();
    await expect(notifier.notify(makeEvent({ result: null }))).resolves.toBeUndefined();
    vi.restoreAllMocks();
  });
});

// ---------------------------------------------------------------------------
// WebhookPushNotifier
// ---------------------------------------------------------------------------

describe('WebhookPushNotifier', () => {
  const WEBHOOK_URL = 'https://example.com/hook';

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    vi.spyOn(console, 'error').mockImplementation(() => {});
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends a POST request to the webhook URL', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockOkResponse());

    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL });
    await notifier.notify(makeEvent());

    expect(fetch).toHaveBeenCalledOnce();
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe(WEBHOOK_URL);
    expect(init.method).toBe('POST');
  });

  it('includes Content-Type: application/json header', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockOkResponse());

    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL });
    await notifier.notify(makeEvent());

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
  });

  it('does NOT include X-A2A-Signature when no secret is set', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockOkResponse());

    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL });
    await notifier.notify(makeEvent());

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers['X-A2A-Signature']).toBeUndefined();
  });

  it('includes X-A2A-Signature header when secret is set', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockOkResponse());

    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL, secret: 'my-secret' });
    await notifier.notify(makeEvent());

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    expect(headers['X-A2A-Signature']).toMatch(/^sha256=[0-9a-f]{64}$/);
  });

  it('HMAC signature is valid and can be verified with Node crypto', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockOkResponse());

    const secret = 'super-secret';
    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL, secret });
    const event = makeEvent();

    await notifier.notify(event);

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const headers = init.headers as Record<string, string>;
    const sentBody = init.body as string;
    const sentSig = headers['X-A2A-Signature'];

    const expectedHex = createHmac('sha256', secret).update(sentBody).digest('hex');
    expect(sentSig).toBe(`sha256=${expectedHex}`);

    const parsed = JSON.parse(sentBody) as PushEvent;
    expect(parsed.skill).toBe(event.skill);
    expect(parsed.result).toEqual(event.result);
  });

  it('resolves cleanly on a 2xx response', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockOkResponse(201));

    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL });
    await expect(notifier.notify(makeEvent())).resolves.toBeUndefined();
  });

  it('logs error and resolves (does not throw) on 4xx after retries', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockErrorResponse(400));

    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL, maxRetries: 1 });
    // Should NOT throw — it logs and swallows
    await expect(notifier.notify(makeEvent())).resolves.toBeUndefined();
    expect(console.error).toHaveBeenCalled();
  });

  it('logs error and resolves (does not throw) on 5xx after exhausting retries', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockErrorResponse(503));

    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL, maxRetries: 2 });
    await expect(notifier.notify(makeEvent())).resolves.toBeUndefined();

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(console.error).toHaveBeenCalled();
  });

  it('retries on network-level errors and succeeds', async () => {
    (fetch as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(new Error('network error'))
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValue(mockOkResponse());

    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL, maxRetries: 3 });

    await expect(notifier.notify(makeEvent())).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it('logs error after all retries on persistent network errors', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('timeout'));

    const notifier = new WebhookPushNotifier({ url: WEBHOOK_URL, maxRetries: 2 });

    await expect(notifier.notify(makeEvent())).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(console.error).toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Agent config wiring: protocolTaskStore
// ---------------------------------------------------------------------------

describe('Agent protocolTaskStore wiring', () => {
  it('accepts a custom protocolTaskStore in config without throwing', () => {
    const store = new InMemoryTaskStore() as unknown as import('@a2a-js/sdk/server').TaskStore;
    expect(() => {
      new Agent({
        name: 'Bot',
        description: 'Test',
        protocolTaskStore: store,
      });
    }).not.toThrow();
  });

  it('builds the app using the provided protocolTaskStore without error', () => {
    const store = new InMemoryTaskStore() as unknown as import('@a2a-js/sdk/server').TaskStore;
    const agent = new Agent({
      name: 'Bot',
      description: 'Test',
      protocolTaskStore: store,
    });
    agent.skill('ping', async () => 'pong');
    expect(() => agent.buildApp()).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Agent config wiring: pushNotifier auto-wiring
// ---------------------------------------------------------------------------

describe('Agent pushNotifier auto-wiring', () => {
  it('calls pushNotifier.notify() after a skill completes', async () => {
    const notifyCalls: PushEvent[] = [];
    const fakeNotifier = {
      notify: vi.fn(async (event: PushEvent) => {
        notifyCalls.push(event);
      }),
    };

    const agent = new Agent({
      name: 'Bot',
      description: 'Test',
      pushNotifier: fakeNotifier as unknown as import('../src/push-notifications.js').PushNotifier,
    });

    agent.skill('echo', async ({ msg }: { msg: string }) => `echo: ${msg}`);

    const client = new AgentTestClient(agent);
    await client.call('echo', { msg: 'hello' });

    expect(fakeNotifier.notify).toHaveBeenCalledOnce();
    const event = notifyCalls[0];
    expect(event.skill).toBe('echo');
    expect(event.result).toBe('echo: hello');
    expect(typeof event.timestamp).toBe('number');
  });

  it('notifier receives result from slow skill', async () => {
    const notifyCalls: PushEvent[] = [];
    const fakeNotifier = {
      notify: vi.fn(async (event: PushEvent) => {
        notifyCalls.push(event);
      }),
    };

    const agent = new Agent({
      name: 'Bot',
      description: 'Test',
      pushNotifier: fakeNotifier as unknown as import('../src/push-notifications.js').PushNotifier,
    });

    agent.skill('slow', async ({ n }: { n: number }) => {
      await new Promise((r) => setTimeout(r, 10));
      return n * 2;
    });

    const client = new AgentTestClient(agent);
    const result = await client.call('slow', { n: 21 });

    expect(result.data).toBe(42);
    expect(notifyCalls[0].result).toBe(42);
  });

  it('advertises pushNotifications capability even when agent-level pushNotifier is absent', () => {
    const agent = new Agent({
      name: 'Bot',
      description: 'Test',
    });

    const card = agent.buildAgentCard();
    // Per-task push notifications are always available via TaskPushRegistry
    expect(card.capabilities?.pushNotifications).toBe(true);
  });

  it('notifier is called for each skill invocation', async () => {
    const fakeNotifier = { notify: vi.fn(async () => {}) };

    const agent = new Agent({
      name: 'Bot',
      description: 'Test',
      pushNotifier: fakeNotifier as unknown as import('../src/push-notifications.js').PushNotifier,
    });

    agent.skill('greet', async ({ name }: { name: string }) => `Hi, ${name}`);

    const client = new AgentTestClient(agent);
    const beforeAlice = fakeNotifier.notify.mock.calls.length;
    await client.call('greet', { name: 'Alice' });
    const afterAlice = fakeNotifier.notify.mock.calls.length;
    await client.call('greet', { name: 'Bob' });
    const afterBob = fakeNotifier.notify.mock.calls.length;

    // Each call should increase the notify count by at least 1
    expect(afterAlice).toBeGreaterThan(beforeAlice);
    expect(afterBob).toBeGreaterThan(afterAlice);
  });
});
