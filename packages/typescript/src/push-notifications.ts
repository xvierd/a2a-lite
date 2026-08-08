/**
 * Push notification support for A2A Lite agents.
 *
 * @example
 * import { Agent } from './agent';
 * import { WebhookPushNotifier } from './push-notifications';
 *
 * const agent = new Agent({
 *   name: 'Bot',
 *   description: '...',
 *   pushNotifier: new WebhookPushNotifier({
 *     url: 'https://my-app.com/webhook/a2a',
 *     secret: 'my-signing-secret',
 *   }),
 * });
 */

import { createHmac } from 'crypto';

/** Event payload sent to push notifiers on skill completion. */
export interface PushEvent {
  skill: string;
  result: unknown;
  status: 'completed' | 'failed';
  timestamp: number;
  agent: string;
}

/**
 * Abstract base class for push notification delivery.
 * Extend this to send events to Slack, queues, webhooks, etc.
 *
 * @example
 * class SlackPushNotifier extends PushNotifier {
 *   async notify(event: PushEvent): Promise<void> {
 *     await fetch(this.slackUrl, {
 *       method: 'POST',
 *       body: JSON.stringify({ text: `${event.skill} completed` }),
 *     });
 *   }
 * }
 */
export abstract class PushNotifier {
  abstract notify(event: PushEvent): Promise<void>;
}

export interface WebhookPushNotifierOptions {
  /** Webhook endpoint URL */
  url: string;
  /**
   * Optional secret for HMAC-SHA256 request signing.
   * Signature sent as X-A2A-Signature header: `sha256=<hex>`
   */
  secret?: string;
  /** Additional HTTP headers */
  headers?: Record<string, string>;
  /** Number of retry attempts on failure (default: 3) */
  maxRetries?: number;
  /** Request timeout in milliseconds (default: 10000) */
  timeoutMs?: number;
}

/**
 * Sends skill completion events as HTTP POST requests to a webhook URL.
 *
 * Features:
 * - Automatic retry with exponential backoff
 * - Optional HMAC-SHA256 request signing
 * - Configurable headers and timeout
 *
 * @example
 * const notifier = new WebhookPushNotifier({
 *   url: 'https://api.example.com/a2a-events',
 *   secret: 'my-webhook-secret',
 *   headers: { 'Authorization': 'Bearer token' },
 *   maxRetries: 3,
 * });
 */
export class WebhookPushNotifier extends PushNotifier {
  private readonly url: string;
  private readonly secret?: string;
  private readonly headers: Record<string, string>;
  private readonly maxRetries: number;
  private readonly timeoutMs: number;

  constructor(options: WebhookPushNotifierOptions) {
    super();
    this.url = options.url;
    this.secret = options.secret;
    this.headers = options.headers ?? {};
    this.maxRetries = options.maxRetries ?? 3;
    this.timeoutMs = options.timeoutMs ?? 10_000;
  }

  private sign(payload: string): string {
    return `sha256=${createHmac('sha256', this.secret!).update(payload).digest('hex')}`;
  }

  async notify(event: PushEvent): Promise<void> {
    const payload = JSON.stringify(event);
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-A2A-Event': event.skill,
      ...this.headers,
    };

    if (this.secret) {
      headers['X-A2A-Signature'] = this.sign(payload);
    }

    let lastError: unknown;

    for (let attempt = 0; attempt < this.maxRetries; attempt++) {
      try {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), this.timeoutMs);

        try {
          const response = await fetch(this.url, {
            method: 'POST',
            body: payload,
            headers,
            signal: controller.signal,
          });

          if (!response.ok) {
            throw new Error(`Webhook responded with ${response.status}`);
          }
          return; // success
        } finally {
          clearTimeout(timer);
        }
      } catch (err) {
        lastError = err;
        if (attempt < this.maxRetries - 1) {
          const waitMs = 1000 * Math.pow(2, attempt); // 1s, 2s, 4s
          await new Promise((resolve) => setTimeout(resolve, waitMs));
        }
      }
    }

    console.error(`[A2A] Push notification failed after ${this.maxRetries} attempts:`, lastError);
  }
}

/**
 * Development notifier that logs events to console.
 * Useful for testing push notification wiring without a real endpoint.
 *
 * @example
 * const agent = new Agent({
 *   name: 'Bot',
 *   description: '...',
 *   pushNotifier: new LogPushNotifier(),
 * });
 */
// ---------------------------------------------------------------------------
// TaskPushRegistry — per-task push notification config store
// ---------------------------------------------------------------------------

/**
 * In-memory registry for per-task push notification configurations.
 *
 * A caller registers a webhook URL (and optional bearer token) for a specific
 * task ID via the `CreateTaskPushNotificationConfig` JSON-RPC method.  When the
 * task completes, the server fires the webhook.
 */
export class TaskPushRegistry {
  private readonly configs = new Map<string, { url: string; token?: string }>();

  set(taskId: string, url: string, token?: string): void {
    this.configs.set(taskId, { url, token });
  }

  get(taskId: string): { url: string; token?: string } | undefined {
    return this.configs.get(taskId);
  }

  delete(taskId: string): boolean {
    return this.configs.delete(taskId);
  }

  has(taskId: string): boolean {
    return this.configs.has(taskId);
  }
}

// ---------------------------------------------------------------------------
// createPushNotificationMiddleware — Express middleware for JSON-RPC methods
// ---------------------------------------------------------------------------

/**
 * Returns Express middleware that intercepts the A2A v1.0 push notification
 * JSON-RPC methods (`CreateTaskPushNotificationConfig`, `GetTaskPushNotificationConfig`,
 * `DeleteTaskPushNotificationConfig`) and manages the per-task registry.
 *
 * Mount this **before** the SDK's `jsonRpcHandler` so that the custom
 * methods are handled without reaching the protocol layer.
 */
export function createPushNotificationMiddleware(registry: TaskPushRegistry) {
  return async (req: any, res: any, next: () => void): Promise<void> => {
    if (req.method !== 'POST' || !req.body) {
      return next();
    }

    const { method, id, params } = req.body;

    if (method === 'CreateTaskPushNotificationConfig') {
      const taskId = params?.taskId;
      const configId = params?.id ?? taskId;
      const url = params?.url;
      const token = params?.token;

      if (!taskId || !url) {
        res.json({
          jsonrpc: '2.0',
          id: id ?? null,
          error: { code: -32602, message: 'Missing required fields: taskId and url' },
        });
        return;
      }

      registry.set(taskId, url, token);

      res.json({
        jsonrpc: '2.0',
        id: id ?? null,
        result: { taskId, id: configId, url, token },
      });
      return;
    }

    if (method === 'GetTaskPushNotificationConfig') {
      const taskId = params?.taskId;
      const configId = params?.id ?? taskId;

      if (!taskId) {
        res.json({
          jsonrpc: '2.0',
          id: id ?? null,
          error: { code: -32602, message: 'Missing taskId' },
        });
        return;
      }

      const config = registry.get(taskId);
      if (!config) {
        res.json({
          jsonrpc: '2.0',
          id: id ?? null,
          error: { code: -32001, message: `No push notification config for task ${taskId}` },
        });
        return;
      }

      res.json({
        jsonrpc: '2.0',
        id: id ?? null,
        result: { taskId, id: configId, url: config.url, token: config.token },
      });
      return;
    }

    if (method === 'DeleteTaskPushNotificationConfig') {
      const taskId = params?.taskId;

      if (!taskId) {
        res.json({
          jsonrpc: '2.0',
          id: id ?? null,
          error: { code: -32602, message: 'Missing taskId' },
        });
        return;
      }

      registry.delete(taskId);
      res.json({
        jsonrpc: '2.0',
        id: id ?? null,
        result: {},
      });
      return;
    }

    return next();
  };
}

// ---------------------------------------------------------------------------
// LogPushNotifier
// ---------------------------------------------------------------------------

export class LogPushNotifier extends PushNotifier {
  async notify(event: PushEvent): Promise<void> {
    console.log('[A2A Push]', {
      skill: event.skill,
      status: event.status,
      agent: event.agent,
      timestamp: new Date(event.timestamp * 1000).toISOString(),
    });
  }
}
