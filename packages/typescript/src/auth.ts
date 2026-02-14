/**
 * Authentication providers for A2A Lite.
 *
 * All optional - only import if needed.
 *
 * Example (no auth - default):
 *   const agent = new Agent({ name: "Bot", description: "Open bot" });
 *
 * Example (with API key):
 *   import { APIKeyAuth } from 'a2a-lite';
 *   const agent = new Agent({
 *     name: "SecureBot",
 *     auth: new APIKeyAuth({ keys: ["secret-key"] }),
 *   });
 *
 * Example (with Bearer token):
 *   import { BearerAuth } from 'a2a-lite';
 *   const agent = new Agent({
 *     name: "JWTBot",
 *     auth: new BearerAuth({
 *       validator: async (token) => verifyJwt(token)?.userId
 *     }),
 *   });
 */

import { createHash } from 'crypto';
import type { AuthProvider, AuthRequest, AuthResult } from './types.js';

/**
 * No authentication (default).
 */
export class NoAuth implements AuthProvider {
  async authenticate(_request: AuthRequest): Promise<AuthResult> {
    return {
      authenticated: true,
      userId: 'anonymous',
      scopes: new Set(['*']),
    };
  }

  getScheme(): Record<string, unknown> {
    return {};
  }
}

/**
 * API Key authentication.
 *
 * Example:
 *   const auth = new APIKeyAuth({ keys: ['secret-key'] });
 *   const agent = new Agent({ name: "Bot", auth });
 */
export class APIKeyAuth implements AuthProvider {
  private keyHashes: Set<string>;
  private header: string;
  private queryParam?: string;

  constructor(options: { keys: string[]; header?: string; queryParam?: string }) {
    // Store only hashes of keys for security
    this.keyHashes = new Set(
      options.keys.map((k) => createHash('sha256').update(k).digest('hex'))
    );
    this.header = options.header ?? 'X-API-Key';
    this.queryParam = options.queryParam;
  }

  private hashKey(key: string): string {
    return createHash('sha256').update(key).digest('hex');
  }

  async authenticate(request: AuthRequest): Promise<AuthResult> {
    // Check header (case-insensitive)
    const headerKey =
      request.headers[this.header] || request.headers[this.header.toLowerCase()];

    if (headerKey) {
      const hash = this.hashKey(headerKey);
      if (this.keyHashes.has(hash)) {
        return {
          authenticated: true,
          userId: `api-key:${hash.slice(0, 16)}`,
          scopes: new Set(['*']),
        };
      }
    }

    // Check query param
    if (this.queryParam && request.queryParams) {
      const queryKey = request.queryParams[this.queryParam];
      if (queryKey) {
        const hash = this.hashKey(queryKey);
        if (this.keyHashes.has(hash)) {
          return {
            authenticated: true,
            userId: `api-key:${hash.slice(0, 16)}`,
            scopes: new Set(['*']),
          };
        }
      }
    }

    // No key provided
    if (!headerKey && !(this.queryParam && request.queryParams?.[this.queryParam])) {
      return {
        authenticated: false,
        error: 'API key required',
      };
    }

    return {
      authenticated: false,
      error: 'Invalid API key',
    };
  }

  getScheme(): Record<string, unknown> {
    return {
      type: 'apiKey',
      in: this.queryParam ? 'query' : 'header',
      name: this.queryParam ?? this.header,
    };
  }
}

/**
 * Bearer token authentication.
 *
 * Example:
 *   const auth = new BearerAuth({
 *     validator: async (token) => {
 *       const user = await verifyJwt(token);
 *       return user?.id ?? null;
 *     }
 *   });
 */
export class BearerAuth implements AuthProvider {
  private validator: (token: string) => Promise<string | null> | string | null;

  constructor(options: {
    validator: (token: string) => Promise<string | null> | string | null;
  }) {
    this.validator = options.validator;
  }

  async authenticate(request: AuthRequest): Promise<AuthResult> {
    const authHeader =
      request.headers['Authorization'] || request.headers['authorization'];

    if (!authHeader) {
      return {
        authenticated: false,
        error: 'Authorization header required',
      };
    }

    if (!authHeader.startsWith('Bearer ')) {
      return {
        authenticated: false,
        error: 'Bearer token required',
      };
    }

    const token = authHeader.slice(7);
    const userId = await this.validator(token);

    if (userId) {
      return {
        authenticated: true,
        userId,
        scopes: new Set(['*']),
      };
    }

    return {
      authenticated: false,
      error: 'Invalid token',
    };
  }

  getScheme(): Record<string, unknown> {
    return {
      type: 'http',
      scheme: 'bearer',
    };
  }
}

/**
 * Composite authentication (try multiple providers).
 *
 * Example:
 *   const auth = new CompositeAuth([
 *     new APIKeyAuth({ keys: ['key1'] }),
 *     new BearerAuth({ validator: ... }),
 *   ]);
 */
export class CompositeAuth implements AuthProvider {
  private providers: AuthProvider[];

  constructor(providers: AuthProvider[]) {
    this.providers = providers;
  }

  async authenticate(request: AuthRequest): Promise<AuthResult> {
    for (const provider of this.providers) {
      const result = await provider.authenticate(request);
      if (result.authenticated) {
        return result;
      }
    }

    return {
      authenticated: false,
      error: 'No valid authentication provided',
    };
  }

  getScheme(): Record<string, unknown> {
    return {
      oneOf: this.providers.map((p) => p.getScheme()),
    };
  }
}

/**
 * OAuth2/OIDC authentication.
 *
 * Validates JWT tokens from an OAuth2 provider.
 *
 * Example:
 *   const auth = new OAuth2Auth({
 *     issuer: 'https://auth.company.com',
 *     audience: 'my-agent',
 *   });
 *
 *   const agent = new Agent({
 *     name: 'EnterpriseBot',
 *     auth,
 *   });
 *
 * Note: Requires jose or jsonwebtoken package for JWT validation.
 * Install with: npm install jose
 */
export class OAuth2Auth implements AuthProvider {
  readonly issuer: string;
  readonly audience: string;
  readonly jwksUri: string;
  readonly algorithms: string[];
  private _jwksClient: unknown = null;

  constructor(options: {
    issuer: string;
    audience: string;
    jwksUri?: string;
    algorithms?: string[];
  }) {
    this.issuer = options.issuer;
    this.audience = options.audience;
    this.jwksUri = options.jwksUri ?? `${options.issuer}/.well-known/jwks.json`;
    this.algorithms = options.algorithms ?? ['RS256'];
  }

  async authenticate(request: AuthRequest): Promise<AuthResult> {
    const authHeader = request.headers['Authorization'] ?? request.headers['authorization'];

    if (!authHeader || !authHeader.startsWith('Bearer ')) {
      return {
        authenticated: false,
        error: 'Bearer token required',
      };
    }

    const token = authHeader.slice(7);

    try {
      // Try to use jose library (recommended)
      // @ts-expect-error jose is an optional peer dependency
      const jose = await import('jose');
      
      const { jwtVerify, createRemoteJWKSet } = jose;
      
      const jwks = createRemoteJWKSet(new URL(this.jwksUri));
      const { payload } = await jwtVerify(token, jwks, {
        issuer: this.issuer,
        audience: this.audience,
        algorithms: this.algorithms,
      });

      const userId = (payload.sub as string) ?? (payload.email as string) ?? 'unknown';
      const scopeString = (payload.scope as string) ?? '';
      const scopes = new Set(scopeString.split(/\s+/).filter(Boolean));

      return {
        authenticated: true,
        userId,
        scopes,
      };
    } catch (error) {
      // jose not installed or validation failed
      if ((error as Error).message?.includes('Cannot find module') || 
          (error as Error).message?.includes('jose')) {
        return {
          authenticated: false,
          error: 'OAuth2 requires jose package. Install with: npm install jose',
        };
      }

      return {
        authenticated: false,
        error: `Token validation failed: ${(error as Error).message}`,
      };
    }
  }

  getScheme(): Record<string, unknown> {
    return {
      type: 'oauth2',
      flows: {
        authorizationCode: {
          authorizationUrl: `${this.issuer}/authorize`,
          tokenUrl: `${this.issuer}/oauth/token`,
          scopes: {},
        },
      },
    };
  }
}
