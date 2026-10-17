import { describe, expect, it, vi } from 'vitest';
import { InMemoryPushNotificationStore, ServerCallContext, type PushNotificationStore } from '@a2a-js/sdk/server';
import type { TaskPushNotificationConfig } from '@a2a-js/sdk';
import { EncryptedPushStore } from '../src/encrypted-push-store.js';

const context = (owner = 'alice', tenant = 'team') =>
  new ServerCallContext({ tenant, user: { userName: owner, isAuthenticated: true } });
const config = (): TaskPushNotificationConfig => ({
  taskId: 'task',
  id: 'hook',
  url: 'https://public.example/hook',
  token: 'token-secret',
  authentication: { scheme: 'Bearer', credentials: 'auth-secret' },
});
const legacy = Buffer.alloc(32, 1);
const next = Buffer.alloc(32, 2);

describe('callback credential encryption boundary', () => {
  it.each([
    Buffer.alloc(31),
    { keys: { 'bad:id': legacy }, activeKeyId: 'bad:id' },
    { keys: { blue: Buffer.alloc(31) }, activeKeyId: 'blue' },
    { keys: { blue: next }, activeKeyId: 'missing' },
    { keys: { blue: next }, activeKeyId: 'blue', legacyKey: Buffer.alloc(31) },
  ])('rejects invalid key configuration before accessing storage', (keys) => {
    const backend = new InMemoryPushNotificationStore();
    expect(() => new EncryptedPushStore(backend, keys)).toThrow();
  });
  it('encrypts both secrets with fresh nonces, preserves caller objects, and assigns a configuration ID', async () => {
    const backend = new InMemoryPushNotificationStore();
    const store = new EncryptedPushStore(backend, legacy);
    const value = config();
    value.id = '';
    await store.save('task', context(), value);
    expect(value.id).toMatch(/^[0-9a-f-]{36}$/);
    expect(value.token).toBe('token-secret');
    const first = await backend.load('task', context());
    expect(JSON.stringify(first)).not.toContain('token-secret');
    expect(JSON.stringify(first)).not.toContain('auth-secret');
    expect(first[0].token).toMatch(/^a2a-enc:v1:/);
    await store.save('task', context(), value);
    expect((await backend.load('task', context()))[0].token).not.toBe(first[0].token);
    expect(await store.load('task', context())).toEqual([value]);
    await store.delete('task', context(), value.id);
    expect(await store.load('task', context())).toEqual([]);
  });
  it('reads old envelopes while writing the active key, and copies keys supplied by the application', async () => {
    const backend = new InMemoryPushNotificationStore();
    await new EncryptedPushStore(backend, legacy).save('task', context(), config());
    const supplied = Buffer.from(next);
    const rotated = new EncryptedPushStore(backend, {
      legacyKey: legacy,
      keys: { green: supplied },
      activeKeyId: 'green',
    });
    supplied.fill(0);
    const value = (await rotated.load('task', context()))[0];
    await rotated.save('task', context(), value);
    expect((await backend.load('task', context()))[0].token).toMatch(/^a2a-enc:v2:green:/);
    expect(
      (
        await new EncryptedPushStore(backend, { keys: { green: next }, activeKeyId: 'green' }).load('task', context())
      )[0],
    ).toEqual(config());
    await expect(
      new EncryptedPushStore(backend, { keys: { blue: legacy }, activeKeyId: 'blue' }).load('task', context()),
    ).rejects.toThrow('key is unavailable');
  });
  it.each(['owner', 'tenant', 'task', 'id', 'url', 'scheme', 'ciphertext'])(
    'rejects tampering with the %s binding',
    async (field) => {
      const backend = new InMemoryPushNotificationStore();
      await new EncryptedPushStore(backend, legacy).save('task', context(), config());
      const encrypted = (await backend.load('task', context()))[0];
      if (field === 'id') encrypted.id = 'another';
      if (field === 'url') encrypted.url = 'https://other.example/hook';
      if (field === 'scheme') encrypted.authentication!.scheme = 'Basic';
      if (field === 'ciphertext') encrypted.token = encrypted.token.slice(0, -3) + 'abc';
      const corrupted: PushNotificationStore = {
        load: async () => [structuredClone(encrypted)],
        save: vi.fn(),
        delete: vi.fn(),
      };
      const store = new EncryptedPushStore(corrupted, legacy);
      await expect(
        store.load(
          field === 'task' ? 'other-task' : 'task',
          context(field === 'owner' ? 'bob' : 'alice', field === 'tenant' ? 'other' : 'team'),
        ),
      ).rejects.toThrow();
    },
  );
  it.each(['plaintext', 'a2a-enc:v1:a', 'a2a-enc:v2:missing:AAAA'])(
    'fails closed for malformed or unreadable credentials',
    async (token) => {
      const backend: PushNotificationStore = {
        load: async () => [{ ...config(), token }],
        save: vi.fn(),
        delete: vi.fn(),
      };
      await expect(new EncryptedPushStore(backend, legacy).load('task', context())).rejects.toThrow();
    },
  );
  it('allows empty credentials without inventing secrets and respects SDK owner scope', async () => {
    const backend = new InMemoryPushNotificationStore();
    const store = new EncryptedPushStore(backend, legacy);
    const empty = { ...config(), token: '', authentication: undefined };
    await store.save('task', context(), empty);
    expect(await store.load('task', context())).toEqual([empty]);
    expect(await store.load('task', context('bob'))).toEqual([]);
  });
});
