import type { Request, RequestHandler } from 'express';
import { UnauthenticatedUser, type User } from '@a2a-js/sdk/server';
import type { UserBuilder } from '@a2a-js/sdk/server/express';
import type { AuthProvider } from './types.js';

/** Keep the verified principal local to this request and share it with both SDK transports. */
export function createHttpAuthentication(provider: AuthProvider): {
  middleware: RequestHandler;
  userBuilder: UserBuilder;
} {
  const principals = new WeakMap<Request, User>();
  const userBuilder: UserBuilder = async (req) => principals.get(req) ?? new UnauthenticatedUser();
  const middleware: RequestHandler = async (req, res, next) => {
    const headers: Record<string, string> = {};
    const queryParams: Record<string, string> = {};
    for (const [key, value] of Object.entries(req.headers)) {
      if (typeof value === 'string') headers[key] = value;
    }
    for (const [key, value] of Object.entries(req.query)) {
      if (typeof value === 'string') queryParams[key] = value;
    }
    try {
      const result = await provider.authenticate({ headers, queryParams });
      if (result.authenticated && typeof result.userId === 'string' && result.userId.trim()) {
        principals.set(req, { isAuthenticated: !result.anonymous, userName: result.userId });
        next();
        return;
      }
    } catch {
      // Provider failures must fail closed without exposing verifier errors or credentials.
    }
    res.status(401).json({ jsonrpc: '2.0', error: { code: -32600, message: 'Authentication failed' } });
  };
  return { middleware, userBuilder };
}
