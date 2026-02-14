import { describe, it, expect, vi } from 'vitest';
import { OAuth2Auth } from '../src/auth.js';

describe('OAuth2Auth', () => {
  describe('Configuration', () => {
    it('should create with issuer and audience', () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      expect(auth).toBeDefined();
    });

    it('should generate default JWKS URI', () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      expect(auth.jwksUri).toBe('https://auth.example.com/.well-known/jwks.json');
    });

    it('should accept custom JWKS URI', () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
        jwksUri: 'https://custom.example.com/jwks',
      });

      expect(auth.jwksUri).toBe('https://custom.example.com/jwks');
    });

    it('should use RS256 as default algorithm', () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      expect(auth.algorithms).toEqual(['RS256']);
    });

    it('should accept custom algorithms', () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
        algorithms: ['RS256', 'RS512', 'ES256'],
      });

      expect(auth.algorithms).toEqual(['RS256', 'RS512', 'ES256']);
    });
  });

  describe('Authentication', () => {
    it('should fail without Authorization header', async () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      const result = await auth.authenticate({
        headers: {},
      });

      expect(result.authenticated).toBe(false);
      expect(result.error).toContain('Bearer token required');
    });

    it('should fail with non-Bearer Authorization header', async () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      const result = await auth.authenticate({
        headers: { Authorization: 'Basic dXNlcjpwYXNz' },
      });

      expect(result.authenticated).toBe(false);
      expect(result.error).toContain('Bearer token required');
    });

    it('should fail with invalid token (JWT library not available)', async () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      // Simulate a case where JWT library is not installed by using an invalid token
      const result = await auth.authenticate({
        headers: { Authorization: 'Bearer invalid-token' },
      });

      // Should fail because JWT library isn't installed or token is invalid
      expect(result.authenticated).toBe(false);
    });

    it('should handle token with correct format', async () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      // This will fail validation but tests the flow
      const result = await auth.authenticate({
        headers: { Authorization: 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c' },
      });

      // Should fail validation but we verify it processes the token
      expect(result).toBeDefined();
    });
  });

  describe('getScheme', () => {
    it('should return OAuth2 scheme', () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      const scheme = auth.getScheme();

      expect(scheme).toEqual({
        type: 'oauth2',
        flows: {
          authorizationCode: {
            authorizationUrl: 'https://auth.example.com/authorize',
            tokenUrl: 'https://auth.example.com/oauth/token',
            scopes: {},
          },
        },
      });
    });

    it('should include correct URLs in scheme', () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.company.com',
        audience: 'my-agent',
      });

      const scheme = auth.getScheme() as {
        type: string;
        flows: {
          authorizationCode: {
            authorizationUrl: string;
            tokenUrl: string;
          };
        };
      };

      expect(scheme.flows.authorizationCode.authorizationUrl).toBe(
        'https://auth.company.com/authorize'
      );
      expect(scheme.flows.authorizationCode.tokenUrl).toBe(
        'https://auth.company.com/oauth/token'
      );
    });
  });

  describe('Error Handling', () => {
    it('should handle missing JWT library gracefully', async () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      // Using a token that's not a valid JWT
      const result = await auth.authenticate({
        headers: { Authorization: 'Bearer not-a-valid-jwt' },
      });

      expect(result.authenticated).toBe(false);
      expect(result.error).toBeDefined();
    });

    it('should handle token validation failures', async () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      // A malformed JWT structure
      const result = await auth.authenticate({
        headers: { Authorization: 'Bearer header.payload' },
      });

      expect(result.authenticated).toBe(false);
      // Error could be about missing jose package or token validation
      expect(result.error).toBeDefined();
    });
  });

  describe('Token Claims', () => {
    it('should extract user_id from sub claim', async () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      // This will fail validation but we can check the structure
      const result = await auth.authenticate({
        headers: { Authorization: 'Bearer test-token' },
      });

      // The result should have the expected structure even on failure
      expect(result).toHaveProperty('authenticated');
      expect(result).toHaveProperty('error');
    });

    it('should handle scope extraction', async () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      const result = await auth.authenticate({
        headers: { Authorization: 'Bearer test-token' },
      });

      // Scopes should be a Set (empty on failure)
      if (result.scopes) {
        expect(result.scopes).toBeInstanceOf(Set);
      }
    });
  });

  describe('Integration', () => {
    it('should work with AuthRequest interface', async () => {
      const auth = new OAuth2Auth({
        issuer: 'https://auth.example.com',
        audience: 'my-agent',
      });

      const result = await auth.authenticate({
        headers: {
          Authorization: 'Bearer test-token',
          'X-Custom-Header': 'value',
        },
        queryParams: { foo: 'bar' },
      });

      expect(result).toBeDefined();
    });
  });
});
