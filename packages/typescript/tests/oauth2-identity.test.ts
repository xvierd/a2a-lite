import { beforeEach, describe, expect, it, vi } from 'vitest';
import { jwtVerify } from 'jose';
import { OAuth2Auth } from '../src/auth.js';

vi.mock('jose', () => ({ jwtVerify: vi.fn(), createRemoteJWKSet: vi.fn() }));

describe('verified OAuth2 identity claims', () => {
  const auth = new OAuth2Auth({ issuer: 'https://issuer.example', audience: 'agent' });
  beforeEach(() => vi.mocked(jwtVerify).mockReset());

  it.each([{}, { sub: '' }, { sub: '  ' }, { sub: 42 }, { email: '' }, { email: [] }])(
    'rejects a verified token without a usable identity: %j',
    async (payload) => {
      vi.mocked(jwtVerify).mockResolvedValue({ payload } as never);
      const result = await auth.authenticate({ headers: { Authorization: 'Bearer signed-token' } });
      expect(result.authenticated).toBe(false);
      expect(result.userId).toBeUndefined();
    },
  );

  it.each([
    { sub: 'alice', scope: 'read write' },
    { email: 'alice', scope: 42 },
  ])('uses a verified identity and safely parses scope: %j', async (payload) => {
    vi.mocked(jwtVerify).mockResolvedValue({ payload } as never);
    const result = await auth.authenticate({ headers: { Authorization: 'Bearer signed-token' } });
    expect(result.authenticated).toBe(true);
    expect(result.userId).toBe('alice');
    expect(result.scopes).toEqual(new Set(typeof payload.scope === 'string' ? ['read', 'write'] : []));
  });
});
