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
          await new Promise(resolve => setTimeout(resolve, waitMs));
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
