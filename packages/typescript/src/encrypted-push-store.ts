import { createCipheriv, createDecipheriv, randomBytes, randomUUID } from 'node:crypto';
import type { PushNotificationStore, ServerCallContext } from '@a2a-js/sdk/server';
import type { TaskPushNotificationConfig } from '@a2a-js/sdk';

export interface CallbackEncryptionKeys {
  /** Legacy v1 decryption key; keep until those rows have been rotated. */
  legacyKey?: Buffer;
  keys: Readonly<Record<string, Buffer>>;
  activeKeyId: string;
}

/** Credential encryption boundary around the official store; keys stay outside the database. */
export class EncryptedPushStore implements PushNotificationStore {
  private readonly legacyKey?: Buffer;
  private readonly keys: Readonly<Record<string, Buffer>>;
  private readonly activeKeyId?: string;
  constructor(
    private readonly store: PushNotificationStore,
    key: Buffer | CallbackEncryptionKeys,
  ) {
    this.legacyKey = Buffer.isBuffer(key) ? Buffer.from(key) : key.legacyKey && Buffer.from(key.legacyKey);
    this.keys = Buffer.isBuffer(key)
      ? {}
      : Object.fromEntries(Object.entries(key.keys).map(([id, value]) => [id, Buffer.from(value)]));
    this.activeKeyId = Buffer.isBuffer(key) ? undefined : key.activeKeyId;
    for (const [id, value] of Object.entries(this.keys)) {
      if (!/^[a-zA-Z0-9_.-]{1,64}$/.test(id)) throw new Error('Invalid callback encryption key ID');
      if (value.length !== 32) throw new Error('Callback encryption key must contain exactly 32 bytes');
    }
    if (this.legacyKey && this.legacyKey.length !== 32)
      throw new Error('Callback encryption key must contain exactly 32 bytes');
    if (!Buffer.isBuffer(key) && (!this.activeKeyId || !Object.hasOwn(this.keys, this.activeKeyId)))
      throw new Error('Active callback encryption key is unavailable');
    if (!this.activeKeyId && !this.legacyKey) throw new Error('Callback encryption key is required');
  }
  private encode(value: string, aad: string): string {
    if (!value) return value;
    const nonce = randomBytes(12);
    const id = this.activeKeyId;
    const cipher = createCipheriv('aes-256-gcm', id ? this.keys[id] : this.legacyKey!, nonce);
    cipher.setAAD(Buffer.from(id ? aad + ':key:' + id : aad));
    return (
      (id ? 'a2a-enc:v2:' + id + ':' : 'a2a-enc:v1:') +
      Buffer.concat([nonce, cipher.update(value, 'utf8'), cipher.final(), cipher.getAuthTag()]).toString('base64url')
    );
  }
  private decode(value: string, aad: string): string {
    if (!value) return value;
    const versioned = /^a2a-enc:v2:([a-zA-Z0-9_.-]{1,64}):([A-Za-z0-9_-]+)$/.exec(value);
    const key = versioned
      ? Object.hasOwn(this.keys, versioned[1])
        ? this.keys[versioned[1]]
        : undefined
      : this.legacyKey;
    if (!versioned && !value.startsWith('a2a-enc:v1:')) throw new Error('Stored callback credential is not encrypted');
    if (!key) throw new Error('Stored callback encryption key is unavailable');
    const bytes = Buffer.from(versioned ? versioned[2] : value.slice(11), 'base64url');
    if (bytes.length < 28) throw new Error('Invalid encrypted callback credential');
    const cipher = createDecipheriv('aes-256-gcm', key, bytes.subarray(0, 12));
    cipher.setAAD(Buffer.from(versioned ? aad + ':key:' + versioned[1] : aad));
    cipher.setAuthTag(bytes.subarray(-16));
    return Buffer.concat([cipher.update(bytes.subarray(12, -16)), cipher.final()]).toString('utf8');
  }
  async save(taskId: string, context: ServerCallContext, config: TaskPushNotificationConfig): Promise<void> {
    if (!config.id) config.id = randomUUID();
    const encrypted = structuredClone(config);
    const aad = this.binding(taskId, context, config);
    encrypted.token = this.encode(encrypted.token, aad + ':token');
    if (encrypted.authentication)
      encrypted.authentication.credentials = this.encode(encrypted.authentication.credentials, aad + ':auth');
    await this.store.save(taskId, context, encrypted);
    config.id = encrypted.id;
  }
  async load(taskId: string, context: ServerCallContext): Promise<TaskPushNotificationConfig[]> {
    return (await this.store.load(taskId, context)).map((config) => {
      const aad = this.binding(taskId, context, config);
      config.token = this.decode(config.token, aad + ':token');
      if (config.authentication)
        config.authentication.credentials = this.decode(config.authentication.credentials, aad + ':auth');
      return config;
    });
  }
  private binding(taskId: string, context: ServerCallContext, config: TaskPushNotificationConfig): string {
    return JSON.stringify([
      context.tenant ?? '',
      context.user?.userName ?? '',
      taskId,
      config.id,
      config.url,
      config.authentication?.scheme ?? '',
    ]);
  }
  delete(taskId: string, context: ServerCallContext, configId?: string): Promise<void> {
    return this.store.delete(taskId, context, configId);
  }
}
