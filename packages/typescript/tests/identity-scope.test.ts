import request from 'supertest';
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { Agent, APIKeyAuth, BearerAuth, type AuthResult } from '../src/index.js';
import { principalKey } from '../src/authorization.js';

function fixture(identities: Record<string, AuthResult>) {
  const agent = new Agent({
    name: 'Scope',
    description: 'Tenant membership',
    auth: {
      getScheme: () => ({ type: 'http', scheme: 'bearer' }),
      authenticate: async ({ headers }) => identities[headers.authorization] ?? { authenticated: false },
    },
  });
  agent.skill('count', { streaming: true }, async function* () {
    yield 'one';
  });
  const app = agent.buildApp();
  const rpc = (user: string, method: string, params: Record<string, unknown> = {}) =>
    request(app)
      .post('/')
      .set('Authorization', user)
      .set('A2A-Version', '1.0')
      .send({ jsonrpc: '2.0', id: '1', method, params });
  const create = async (user: string, tenant = '') =>
    rpc(user, 'SendMessage', {
      tenant,
      message: { messageId: 'm', role: 'ROLE_USER', parts: [{ text: '{"skill":"count"}' }] },
    });
  return { app, rpc, create };
}

describe('trusted identity and tenant membership', () => {
  const vectors = JSON.parse(
    readFileSync(new URL('../../../tests/contracts/identity.json', import.meta.url), 'utf8'),
  ).vectors;
  it.each(vectors)('matches shared principal vector $userId / $namespace / $tenant', (vector) => {
    expect(principalKey(vector.userId, vector.namespace ?? undefined)).toBe(vector.principalKey);
  });
  it('preserves legacy keys and escapes reserved keys without aliasing namespaced users', () => {
    expect(principalKey(' alice ')).toBe(' alice ');
    const encoded = principalKey('alice', 'issuer');
    expect(encoded).toBe('a2a:v1:WyJpc3N1ZXIiLCJhbGljZSJd');
    expect(principalKey(encoded)).not.toBe(encoded);
    expect(principalKey('alice', 'another')).not.toBe(encoded);
  });
  it('defaults to the empty tenant and rejects unsolicited tenant selection before execution', async () => {
    const { app, create, rpc } = fixture({ alice: { authenticated: true, userId: 'alice' } });
    expect((await create('alice')).body.result.task.id).toBeTruthy();
    expect((await create('alice', 'private')).body.error.code).toBe(-32001);
    expect((await rpc('alice', 'ListTasks', { tenant: 'private' })).body.error.code).toBe(-32001);
    await request(app).get('/private/tasks').set('Authorization', 'alice').set('A2A-Version', '1.0').expect(404);
  });
  it('isolates namespaces and two allowed tenants for the same principal across task operations', async () => {
    const { create, rpc } = fixture({
      one: { authenticated: true, userId: 'same', namespace: 'one', authorizedTenants: ['a', 'b'] },
      two: { authenticated: true, userId: 'same', namespace: 'two', authorizedTenants: ['a', 'b'] },
    });
    const id = (await create('one', 'a')).body.result.task.id;
    expect((await rpc('one', 'GetTask', { id, tenant: 'a' })).body.result.id).toBe(id);
    for (const [user, tenant] of [
      ['one', 'b'],
      ['two', 'a'],
    ]) {
      for (const method of ['GetTask', 'CancelTask', 'SubscribeToTask']) {
        expect((await rpc(user, method, { id, tenant })).body.error.code).toBe(-32001);
      }
      expect((await rpc(user, 'ListTasks', { tenant })).body.result.tasks ?? []).toEqual([]);
      expect((await rpc(user, 'ListTaskPushNotificationConfigs', { taskId: id, tenant })).body.error.code).toBe(-32001);
    }
  });
  it('rotates credentials while retaining the configured stable identity and tenant claims', async () => {
    const auth = new APIKeyAuth({
      identities: {
        old: { userId: 'service', namespace: 'org', authorizedTenants: ['a'] },
        next: { userId: 'service', namespace: 'org', authorizedTenants: ['a'] },
      },
    });
    const old = await auth.authenticate({ headers: { 'x-api-key': 'old' } });
    const next = await auth.authenticate({ headers: { 'x-api-key': 'next' } });
    expect(next).toEqual(old);
    expect(next.userId).toBe('service');
    const bearer = new BearerAuth({
      validator: () => ({ userId: 'service', namespace: 'org', authorizedTenants: ['a'] }),
    });
    expect(await bearer.authenticate({ headers: { authorization: 'Bearer opaque' } })).toMatchObject({
      userId: 'service',
      namespace: 'org',
      authorizedTenants: ['a'],
    });
  });
  it.each([{ userId: ' ' }, { userId: 'alice', namespace: ' ' }, { userId: 'alice', authorizedTenants: 'a' }])(
    'fails closed for malformed verified scope: %j',
    async (claims) => {
      const { create } = fixture({ alice: { authenticated: true, ...claims } as AuthResult });
      expect((await create('alice')).status).toBe(401);
    },
  );
});
