import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  TaskPushRegistry,
  createPushNotificationMiddleware,
} from '../src/push-notifications.js';
import {
  setTaskPushNotification,
  getTaskPushNotification,
  deleteTaskPushNotification,
  TaskHandle,
} from '../src/orchestration.js';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockReq(body: Record<string, unknown>) {
  return { method: 'POST', body } as any;
}

function mockRes() {
  const res: any = {
    _json: null,
    json(data: unknown) {
      res._json = data;
      return res;
    },
  };
  return res;
}

function mockJsonResponse(body: Record<string, unknown>, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? 'OK' : 'Error',
    json: () => Promise.resolve(body),
  } as Response;
}

// ---------------------------------------------------------------------------
// TaskPushRegistry
// ---------------------------------------------------------------------------

describe('TaskPushRegistry', () => {
  it('set/get stores and retrieves a config', () => {
    const registry = new TaskPushRegistry();
    registry.set('task-1', 'http://example.com/hook');
    expect(registry.get('task-1')).toEqual({ url: 'http://example.com/hook', token: undefined });
  });

  it('set/get stores url and token', () => {
    const registry = new TaskPushRegistry();
    registry.set('task-2', 'http://example.com/hook', 'secret-token');
    expect(registry.get('task-2')).toEqual({ url: 'http://example.com/hook', token: 'secret-token' });
  });

  it('get returns undefined for missing key', () => {
    const registry = new TaskPushRegistry();
    expect(registry.get('nonexistent')).toBeUndefined();
  });

  it('has returns true for existing key', () => {
    const registry = new TaskPushRegistry();
    registry.set('task-3', 'http://x');
    expect(registry.has('task-3')).toBe(true);
  });

  it('has returns false for missing key', () => {
    const registry = new TaskPushRegistry();
    expect(registry.has('nope')).toBe(false);
  });

  it('delete removes a config', () => {
    const registry = new TaskPushRegistry();
    registry.set('task-4', 'http://x');
    expect(registry.delete('task-4')).toBe(true);
    expect(registry.get('task-4')).toBeUndefined();
  });

  it('delete returns false for missing key', () => {
    const registry = new TaskPushRegistry();
    expect(registry.delete('missing')).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// createPushNotificationMiddleware
// ---------------------------------------------------------------------------

describe('createPushNotificationMiddleware', () => {
  let registry: TaskPushRegistry;
  let middleware: ReturnType<typeof createPushNotificationMiddleware>;

  beforeEach(() => {
    registry = new TaskPushRegistry();
    middleware = createPushNotificationMiddleware(registry);
  });

  it('CreateTaskPushNotificationConfig stores config and returns success', async () => {
    const req = mockReq({
      method: 'CreateTaskPushNotificationConfig',
      id: '1',
      params: {
        taskId: 'task-100',
        url: 'http://hook.test/cb',
        token: 'tok',
      },
    });
    const res = mockRes();
    const next = vi.fn();

    await middleware(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res._json).toEqual({
      jsonrpc: '2.0',
      id: '1',
      result: {
        taskId: 'task-100',
        id: 'task-100',
        url: 'http://hook.test/cb',
        token: 'tok',
      },
    });
    expect(registry.get('task-100')).toEqual({ url: 'http://hook.test/cb', token: 'tok' });
  });

  it('CreateTaskPushNotificationConfig returns error when params are missing', async () => {
    const req = mockReq({
      method: 'CreateTaskPushNotificationConfig',
      id: '2',
      params: {},
    });
    const res = mockRes();
    const next = vi.fn();

    await middleware(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res._json.error.code).toBe(-32602);
  });

  it('GetTaskPushNotificationConfig returns config when present', async () => {
    registry.set('task-200', 'http://hook.test', 'abc');

    const req = mockReq({
      method: 'GetTaskPushNotificationConfig',
      id: '3',
      params: { taskId: 'task-200' },
    });
    const res = mockRes();
    const next = vi.fn();

    await middleware(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res._json.result).toEqual({
      taskId: 'task-200',
      id: 'task-200',
      url: 'http://hook.test',
      token: 'abc',
    });
  });

  it('GetTaskPushNotificationConfig returns error when config is missing', async () => {
    const req = mockReq({
      method: 'GetTaskPushNotificationConfig',
      id: '4',
      params: { taskId: 'no-such-task' },
    });
    const res = mockRes();
    const next = vi.fn();

    await middleware(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res._json.error.code).toBe(-32001);
  });

  it('DeleteTaskPushNotificationConfig removes config and returns success', async () => {
    registry.set('task-300', 'http://hook.test');

    const req = mockReq({
      method: 'DeleteTaskPushNotificationConfig',
      id: '5',
      params: { taskId: 'task-300' },
    });
    const res = mockRes();
    const next = vi.fn();

    await middleware(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res._json.result).toEqual({});
    expect(registry.has('task-300')).toBe(false);
  });

  it('unknown method calls next()', async () => {
    const req = mockReq({
      method: 'SendMessage',
      id: '6',
      params: {},
    });
    const res = mockRes();
    const next = vi.fn();

    await middleware(req, res, next);

    expect(next).toHaveBeenCalledOnce();
    expect(res._json).toBeNull();
  });

  it('non-POST request calls next()', async () => {
    const req = { method: 'GET', body: null } as any;
    const res = mockRes();
    const next = vi.fn();

    await middleware(req, res, next);

    expect(next).toHaveBeenCalledOnce();
  });

  it('uses params.id as config id when provided', async () => {
    const req = mockReq({
      method: 'CreateTaskPushNotificationConfig',
      id: '7',
      params: {
        taskId: 'task-alt',
        id: 'cfg-1',
        url: 'http://alt.test',
      },
    });
    const res = mockRes();
    const next = vi.fn();

    await middleware(req, res, next);

    expect(res._json.result.taskId).toBe('task-alt');
    expect(res._json.result.id).toBe('cfg-1');
    expect(registry.get('task-alt')).toEqual({ url: 'http://alt.test', token: undefined });
  });
});

// ---------------------------------------------------------------------------
// Client functions: setTaskPushNotification / get / delete
// ---------------------------------------------------------------------------

describe('setTaskPushNotification()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends correct JSON-RPC body', async () => {
    const responseBody = { result: { taskId: 't1' } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    await setTaskPushNotification('http://agent', 't1', 'http://hook', 'tok');

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.method).toBe('CreateTaskPushNotificationConfig');
    expect(body.params.taskId).toBe('t1');
    expect(body.params.url).toBe('http://hook');
    expect(body.params.token).toBe('tok');
  });

  it('omits token when not provided', async () => {
    const responseBody = { result: { taskId: 't2' } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    await setTaskPushNotification('http://agent', 't2', 'http://hook');

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.params.token).toBeUndefined();
  });
});

describe('getTaskPushNotification()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends correct JSON-RPC body', async () => {
    const responseBody = { result: { taskId: 't1', pushNotificationConfig: { url: 'http://hook' } } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    await getTaskPushNotification('http://agent', 't1');

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.method).toBe('GetTaskPushNotificationConfig');
    expect(body.params.taskId).toBe('t1');
  });
});

describe('deleteTaskPushNotification()', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends correct JSON-RPC body', async () => {
    const responseBody = { result: { taskId: 't1', deleted: true } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    await deleteTaskPushNotification('http://agent', 't1');

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.method).toBe('DeleteTaskPushNotificationConfig');
    expect(body.params.taskId).toBe('t1');
  });
});

// ---------------------------------------------------------------------------
// TaskHandle — subscribe / unsubscribe / getPushConfig
// ---------------------------------------------------------------------------

describe('TaskHandle push notification methods', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('subscribe() calls setTaskPushNotification with correct args', async () => {
    const responseBody = { result: { taskId: 'h1' } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    const handle = new TaskHandle('h1', 'some-result', 'http://agent:8787');
    await handle.subscribe('http://my-hook', 'my-token');

    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    expect(url).toBe('http://agent:8787');
    const body = JSON.parse(init.body as string);
    expect(body.method).toBe('CreateTaskPushNotificationConfig');
    expect(body.params.taskId).toBe('h1');
    expect(body.params.url).toBe('http://my-hook');
    expect(body.params.token).toBe('my-token');
  });

  it('unsubscribe() calls deleteTaskPushNotification', async () => {
    const responseBody = { result: { taskId: 'h2', deleted: true } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    const handle = new TaskHandle('h2', 'result', 'http://agent:8787');
    await handle.unsubscribe();

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.method).toBe('DeleteTaskPushNotificationConfig');
    expect(body.params.taskId).toBe('h2');
  });

  it('getPushConfig() calls getTaskPushNotification', async () => {
    const responseBody = { result: { taskId: 'h3', pushNotificationConfig: { url: 'http://x' } } };
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValue(mockJsonResponse(responseBody));

    const handle = new TaskHandle('h3', 'result', 'http://agent:8787');
    await handle.getPushConfig();

    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.method).toBe('GetTaskPushNotificationConfig');
    expect(body.params.taskId).toBe('h3');
  });
});
