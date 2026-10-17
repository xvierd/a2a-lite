import { InMemoryPushNotificationStore, V1PushNotificationSerializer } from '@a2a-js/sdk/server';
import type { PushNotificationSender, PushNotificationStore, ServerCallContext } from '@a2a-js/sdk/server';
import type { Task, TaskPushNotificationConfig, StreamResponse } from '@a2a-js/sdk';
import { RequestMalformedError } from '@a2a-js/sdk/errors';
import { z } from 'zod';
import { postWebhook, parseWebhookUrl, resolveWebhookTarget } from './push-delivery.js';

const headerValue = z
  .string()
  .max(8192)
  .refine((value) => !/[\r\n]/.test(value));
const configSchema = z
  .object({
    url: z.string(),
    id: z
      .string()
      .max(256)
      .refine((value) => !/[\x00-\x1f\x7f]/.test(value)),
    token: headerValue.optional(),
    authentication: z
      .object({
        scheme: z.string().regex(/^[A-Za-z][A-Za-z0-9_-]*$/),
        credentials: headerValue,
      })
      .optional(),
  })
  .passthrough();

function authenticatedOwner(context: ServerCallContext): string {
  if (!context.user?.isAuthenticated || !context.user.userName?.trim()) {
    throw new RequestMalformedError('Authentication is required for task push notifications.');
  }
  return context.user.userName;
}

/** Use the SDK's tenant/owner/config scoping and validate callbacks on every registration path. */
export class ProtocolPushStore implements PushNotificationStore {
  private readonly writes = new Map<string, Promise<void>>();
  constructor(
    private readonly backend: PushNotificationStore = new InMemoryPushNotificationStore(authenticatedOwner),
    private readonly maxConfigs = 8,
  ) {}

  async load(taskId: string, context: ServerCallContext): Promise<TaskPushNotificationConfig[]> {
    authenticatedOwner(context);
    return this.backend.load(taskId, context);
  }
  async delete(taskId: string, context: ServerCallContext, configId?: string): Promise<void> {
    authenticatedOwner(context);
    return this.backend.delete(taskId, context, configId);
  }

  async save(taskId: string, context: ServerCallContext, config: TaskPushNotificationConfig): Promise<void> {
    authenticatedOwner(context);
    if (!configSchema.safeParse(config).success) {
      throw new RequestMalformedError('Invalid push notification configuration.');
    }
    try {
      if (parseWebhookUrl(config.url).protocol !== 'https:') throw new Error('HTTPS is required.');
      await resolveWebhookTarget(config.url, AbortSignal.timeout(5000));
    } catch {
      throw new RequestMalformedError('Push notification URL must use HTTPS and resolve only to public addresses.');
    }
    const key = JSON.stringify([context.tenant, context.user?.userName, taskId]);
    const previous = this.writes.get(key) ?? Promise.resolve();
    const write = previous
      .catch(() => {})
      .then(async () => {
        const configs = await this.backend.load(taskId, context);
        if (!configs.some((existing) => existing.id === config.id) && configs.length >= this.maxConfigs)
          throw new RequestMalformedError('Push notification configuration limit reached.');
        await this.backend.save(taskId, context, config);
      });
    this.writes.set(key, write);
    try {
      await write;
    } finally {
      if (this.writes.get(key) === write) this.writes.delete(key);
    }
  }
}

/** Keep the official v1.0 wire serializer and scoped stores, with hardened outbound delivery. */
export class ProtocolPushSender implements PushNotificationSender {
  private readonly serializer = new V1PushNotificationSerializer();
  private readonly deliveries = new Map<string, Promise<void>>();

  constructor(private readonly store: PushNotificationStore) {}

  async send(response: StreamResponse, context: ServerCallContext, task?: Task): Promise<void> {
    if (!context.user?.isAuthenticated) return;
    const payload = response.payload;
    if (!payload) return;
    const taskId = payload.$case === 'task' ? payload.value.id : payload.value.taskId;
    if (!taskId) return;
    const configs = await this.store.load(taskId, context);
    const key = JSON.stringify([context.tenant, context.user?.userName, taskId]);
    const preceding = this.deliveries.get(key) ?? Promise.resolve();
    const pending = preceding
      .catch(() => {})
      .then(async () => {
        const { body, contentType } = this.serializer.serialize(response, task);
        await Promise.all(
          configs.map(async (config) => {
            const headers: Record<string, string> = { 'Content-Type': contentType };
            if (config.authentication?.scheme && config.authentication.credentials) {
              headers.Authorization = `${config.authentication.scheme} ${config.authentication.credentials}`;
            }
            if (config.token) {
              headers['X-A2A-Notification-Token'] = config.token;
            }
            try {
              await postWebhook(config.url, { body, headers, timeoutMs: 5000 });
            } catch {
              // URLs and authentication material must not leak through delivery errors.
              console.warn('[A2A] Push notification delivery failed.');
            }
          }),
        );
      });
    this.deliveries.set(key, pending);
    try {
      await pending;
    } finally {
      if (this.deliveries.get(key) === pending) this.deliveries.delete(key);
    }
  }
}
