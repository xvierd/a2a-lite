import type { Request, RequestHandler } from 'express';
import {
  UnauthenticatedUser,
  defaultServerCallContextBuilder,
  type ServerCallContextBuilder,
  type User,
} from '@a2a-js/sdk/server';
import type { UserBuilder } from '@a2a-js/sdk/server/express';
import type { AuthProvider, AuthResult } from './types.js';
import { AUTH_RESULT, principalKey } from './authorization.js';

/** Keep the verified principal local to this request and share it with both SDK transports. */
export function createHttpAuthentication(
  provider: AuthProvider,
  requireIdentity = false,
): {
  middleware: RequestHandler;
  userBuilder: UserBuilder;
  contextBuilder: ServerCallContextBuilder;
} {
  const principals = new WeakMap<Request, User>();
  const results = new WeakMap<User, AuthResult>();
  const userBuilder: UserBuilder = async (req) => principals.get(req) ?? new UnauthenticatedUser();
  const contextBuilder: ServerCallContextBuilder = (options) => {
    const context = defaultServerCallContextBuilder(options);
    if (options.user) context.state.set(AUTH_RESULT, results.get(options.user));
    return context;
  };
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
      if (requireIdentity && result.anonymous) throw new Error('Authenticated identity required');
      if (result.authenticated && typeof result.userId === 'string' && result.userId.trim()) {
        if (result.namespace !== undefined && (typeof result.namespace !== 'string' || !result.namespace.trim()))
          throw new Error('Invalid identity namespace');
        if (
          result.authorizedTenants !== undefined &&
          (!(Array.isArray(result.authorizedTenants) || result.authorizedTenants instanceof Set) ||
            Array.from(result.authorizedTenants).some((tenant) => typeof tenant !== 'string'))
        )
          throw new Error('Invalid tenant membership');
        const user = { isAuthenticated: !result.anonymous, userName: principalKey(result.userId, result.namespace) };
        principals.set(req, user);
        if (res.locals) res.locals.a2aPrincipal = user.userName;
        results.set(user, { ...result, authorizedTenants: [...(result.authorizedTenants ?? [''])] });
        next();
        return;
      }
    } catch {
      // Provider failures must fail closed without exposing verifier errors or credentials.
    }
    res.status(401).json({ jsonrpc: '2.0', error: { code: -32600, message: 'Authentication failed' } });
  };
  return { middleware, userBuilder, contextBuilder };
}
