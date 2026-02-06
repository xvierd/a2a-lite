import { describe, it, expect } from 'vitest';
import { NoAuth, APIKeyAuth, BearerAuth, CompositeAuth } from '../src/auth.js';

describe('NoAuth', () => {
  it('should always authenticate', async () => {
    const auth = new NoAuth();
    const result = await auth.authenticate({ headers: {} });

    expect(result.authenticated).toBe(true);
    expect(result.userId).toBe('anonymous');
  });

  it('should return empty scheme', () => {
    const auth = new NoAuth();
    expect(auth.getScheme()).toEqual({});
  });
});

describe('APIKeyAuth', () => {
  it('should authenticate with valid key in header', async () => {
    const auth = new APIKeyAuth({ keys: ['secret-key', 'another-key'] });
    const result = await auth.authenticate({
      headers: { 'X-API-Key': 'secret-key' },
    });

    expect(result.authenticated).toBe(true);
  });

  it('should reject invalid key', async () => {
    const auth = new APIKeyAuth({ keys: ['secret-key'] });
    const result = await auth.authenticate({
      headers: { 'X-API-Key': 'wrong-key' },
    });

    expect(result.authenticated).toBe(false);
    expect(result.error).toContain('Invalid');
  });

  it('should reject missing key', async () => {
    const auth = new APIKeyAuth({ keys: ['secret-key'] });
    const result = await auth.authenticate({ headers: {} });

    expect(result.authenticated).toBe(false);
    expect(result.error).toContain('required');
  });

  it('should support custom header', async () => {
    const auth = new APIKeyAuth({ keys: ['key123'], header: 'Authorization' });
    const result = await auth.authenticate({
      headers: { Authorization: 'key123' },
    });

    expect(result.authenticated).toBe(true);
  });

  it('should support query param', async () => {
    const auth = new APIKeyAuth({ keys: ['key123'], queryParam: 'api_key' });
    const result = await auth.authenticate({
      headers: {},
      queryParams: { api_key: 'key123' },
    });

    expect(result.authenticated).toBe(true);
  });

  it('should return correct scheme', () => {
    const auth = new APIKeyAuth({ keys: ['key'], header: 'X-API-Key' });
    const scheme = auth.getScheme();

    expect(scheme.type).toBe('apiKey');
    expect(scheme.in).toBe('header');
    expect(scheme.name).toBe('X-API-Key');
  });
});

describe('BearerAuth', () => {
  it('should authenticate with valid token', async () => {
    const auth = new BearerAuth({
      validator: (token) => (token === 'valid-token' ? 'user-123' : null),
    });

    const result = await auth.authenticate({
      headers: { Authorization: 'Bearer valid-token' },
    });

    expect(result.authenticated).toBe(true);
    expect(result.userId).toBe('user-123');
  });

  it('should reject invalid token', async () => {
    const auth = new BearerAuth({
      validator: () => null,
    });

    const result = await auth.authenticate({
      headers: { Authorization: 'Bearer invalid' },
    });

    expect(result.authenticated).toBe(false);
  });

  it('should reject missing Bearer prefix', async () => {
    const auth = new BearerAuth({
      validator: () => 'user',
    });

    const result = await auth.authenticate({
      headers: { Authorization: 'token-without-bearer' },
    });

    expect(result.authenticated).toBe(false);
  });

  it('should return correct scheme', () => {
    const auth = new BearerAuth({ validator: () => null });
    const scheme = auth.getScheme();

    expect(scheme.type).toBe('http');
    expect(scheme.scheme).toBe('bearer');
  });
});

describe('CompositeAuth', () => {
  it('should authenticate with first matching provider', async () => {
    const auth = new CompositeAuth([
      new APIKeyAuth({ keys: ['api-key'] }),
      new BearerAuth({ validator: (t) => (t === 'token' ? 'bearer-user' : null) }),
    ]);

    // API key should work
    const result1 = await auth.authenticate({
      headers: { 'X-API-Key': 'api-key' },
    });
    expect(result1.authenticated).toBe(true);

    // Bearer should also work
    const result2 = await auth.authenticate({
      headers: { Authorization: 'Bearer token' },
    });
    expect(result2.authenticated).toBe(true);
  });

  it('should reject when all providers fail', async () => {
    const auth = new CompositeAuth([
      new APIKeyAuth({ keys: ['key1'] }),
      new APIKeyAuth({ keys: ['key2'] }),
    ]);

    const result = await auth.authenticate({
      headers: { 'X-API-Key': 'wrong' },
    });

    expect(result.authenticated).toBe(false);
  });
});
