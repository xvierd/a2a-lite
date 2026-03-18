/**
 * Push notification support for A2A Lite.
 *
 * PushNotifier lets you fire-and-forget events when a skill completes.
 *
 * Simple (dev):
 *   const agent = new Agent({
 *     name: "Bot",
 *     description: "My bot",
 *     pushNotifier: new LogPushNotifier(),
 *   });
 *
 * Production (webhook + HMAC signature):
 *   const agent = new Agent({
 *     name: "Bot",
 *     description: "My bot",
 *     pushNotifier: new WebhookPushNotifier({
 *       url: process.env.WEBHOOK_URL!,
 *       secret: process.env.WEBHOOK_SECRET,
 *     }),
 *   });
 */

import { createHmac } from 'crypto';

/**
 * The payload delivered on every skill completion event.
 */
export interface PushEvent {
  /** Skill that was executed. */
  skill: string;
  /** Value returned by the skill handler. */
  result: unknown;
  /** ISO timestamp of when the event was fired. */
  timestamp: string;
}

/**
 * Abstract base class for push notifiers.
 * Extend this to build custom notification backends.
 */
export abstract class PushNotifier {
  abstract notify(event: PushEvent): Promise<void>;
}

/**
 * Logs every push event to console.  Useful during development.
 */
export class LogPushNotifier extends PushNotifier {
  async notify(event: PushEvent): Promise<void> {
    console.log('[PushNotifier]', JSON.stringify(event));
  }
}

/**
 * Sends push events as HTTP POST requests to a webhook URL.
 *
 * Features:
 *   - Optional HMAC-SHA256 signature via `X-A2A-Signature` header
 *   - Configurable retry with exponential back-off
 *   - Throws `WebhookPushError` after all retries are exhausted
 */
export interface WebhookPushNotifierOptions {
  /** Webhook endpoint to POST events to. */
  url: string;
  /**
   * Optional HMAC-SHA256 secret.  When set, every request will include an
   * `X-A2A-Signature: sha256=<hex>` header so the receiver can verify origin.
   */
  secret?: string;
  /** Maximum number of attempts (default: 3). */
  maxRetries?: number;
  /** Base delay between retries in ms (default: 500).  Doubles each attempt. */
  retryDelayMs?: number;
}

export class WebhookPushError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number
  ) {
    super(message);
    this.name = 'WebhookPushError';
  }
}

export class WebhookPushNotifier extends PushNotifier {
  private readonly url: string;
  private readonly secret?: string;
  private readonly maxRetries: number;
  private readonly retryDelayMs: number;

  constructor(options: WebhookPushNotifierOptions) {
    super();
    this.url = options.url;
    this.secret = options.secret;
    this.maxRetries = options.maxRetries ?? 3;
    this.retryDelayMs = options.retryDelayMs ?? 500;
  }

  async notify(event: PushEvent): Promise<void> {
    const body = JSON.stringify(event);
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (this.secret) {
      const sig = createHmac('sha256', this.secret).update(body).digest('hex');
      headers['X-A2A-Signature'] = `sha256=${sig}`;
    }

    let lastError: Error | undefined;
    let delay = this.retryDelayMs;

    for (let attempt = 1; attempt <= this.maxRetries; attempt++) {
      try {
        const response = await fetch(this.url, {
          method: 'POST',
          headers,
          body,
        });

        if (response.ok) {
          return; // Success
        }

        // 4xx errors are not retryable
        if (response.status >= 400 && response.status < 500) {
          throw new WebhookPushError(
            `Webhook rejected with status ${response.status}`,
            response.status
          );
        }

        // 5xx — retryable
        lastError = new WebhookPushError(
          `Webhook server error: ${response.status}`,
          response.status
        );
      } catch (err) {
        if (err instanceof WebhookPushError && err.statusCode && err.statusCode < 500) {
          // Non-retryable client error — re-throw immediately
          throw err;
        }
        lastError = err instanceof Error ? err : new Error(String(err));
      }

      if (attempt < this.maxRetries) {
        await new Promise((resolve) => setTimeout(resolve, delay));
        delay *= 2;
      }
    }

    throw lastError ?? new WebhookPushError('Unknown webhook error');
  }
}
