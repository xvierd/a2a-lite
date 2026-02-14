/**
 * Built-in middlewares for A2A Lite.
 *
 * Middleware allows you to add cross-cutting concerns like logging,
 * rate limiting, error handling, etc.
 *
 * Example:
 *   import { loggingMiddleware, rateLimitMiddleware } from 'a2a-lite';
 *
 *   agent.use(loggingMiddleware());
 *   agent.use(rateLimitMiddleware({ requestsPerMinute: 100 }));
 */

import type { Middleware, MiddlewareContext, MiddlewareNext } from '../types.js';

/**
 * Logging middleware.
 *
 * Logs skill calls and their results.
 *
 * Example:
 *   agent.use(loggingMiddleware());
 *
 *   // Or with custom logger
 *   agent.use(loggingMiddleware({ logger: customLogger }));
 */
export function loggingMiddleware(options?: {
  logger?: { info: (msg: string) => void; error: (msg: string) => void };
}): Middleware {
  const logger = options?.logger ?? {
    info: (msg: string) => console.log(`[A2A] ${msg}`),
    error: (msg: string) => console.error(`[A2A] ${msg}`),
  };

  return async (ctx: MiddlewareContext, next: MiddlewareNext) => {
    const start = Date.now();
    logger.info(`Calling skill: ${ctx.skill}`);

    try {
      const result = await next();
      const elapsed = Date.now() - start;
      logger.info(`Skill ${ctx.skill} completed in ${elapsed}ms`);
      return result;
    } catch (error) {
      const elapsed = Date.now() - start;
      logger.error(`Skill ${ctx.skill} failed after ${elapsed}ms: ${(error as Error).message}`);
      throw error;
    }
  };
}

/**
 * Rate limiting middleware.
 *
 * Limits the number of requests per minute.
 * Note: This is an in-memory rate limiter. For production use,
 * consider using a Redis-backed rate limiter.
 *
 * Example:
 *   agent.use(rateLimitMiddleware({ requestsPerMinute: 60 }));
 */
export function rateLimitMiddleware(options: {
  requestsPerMinute: number;
  windowMs?: number;
  errorMessage?: string;
}): Middleware {
  const { requestsPerMinute, windowMs = 60000, errorMessage } = options;
  const requests: number[] = [];

  return async (ctx: MiddlewareContext, next: MiddlewareNext) => {
    const now = Date.now();
    const windowStart = now - windowMs;

    // Remove old requests
    while (requests.length > 0 && requests[0] < windowStart) {
      requests.shift();
    }

    // Check if limit exceeded
    if (requests.length >= requestsPerMinute) {
      throw new Error(errorMessage ?? `Rate limit exceeded: ${requestsPerMinute} requests per minute`);
    }

    // Add current request
    requests.push(now);

    return await next();
  };
}

/**
 * Error handling middleware.
 *
 * Catches errors and formats them into a consistent response.
 *
 * Example:
 *   agent.use(errorHandlingMiddleware());
 *
 *   // Or with custom error handler
 *   agent.use(errorHandlingMiddleware({
 *     onError: (error) => ({ error: error.message })
 *   }));
 */
export function errorHandlingMiddleware(options?: {
  onError?: (error: Error, ctx: MiddlewareContext) => unknown;
  includeStack?: boolean;
}): Middleware {
  return async (ctx: MiddlewareContext, next: MiddlewareNext) => {
    try {
      return await next();
    } catch (error) {
      if (options?.onError) {
        return options.onError(error as Error, ctx);
      }

      return {
        error: (error as Error).message,
        type: (error as Error).constructor.name,
        ...(options?.includeStack && { stack: (error as Error).stack }),
      };
    }
  };
}

/**
 * Timing middleware.
 *
 * Adds execution time to the metadata.
 *
 * Example:
 *   agent.use(timingMiddleware());
 *
 *   // Access timing in subsequent middleware or skill
 *   agent.use(async (ctx, next) => {
 *     await next();
 *     console.log(`Took ${ctx.metadata.executionTimeMs}ms`);
 *   });
 */
export function timingMiddleware(): Middleware {
  return async (ctx: MiddlewareContext, next: MiddlewareNext) => {
    const start = Date.now();
    const result = await next();
    const elapsed = Date.now() - start;
    ctx.metadata.executionTimeMs = elapsed;
    return result;
  };
}

/**
 * Request ID middleware.
 *
 * Adds a unique request ID to the metadata.
 *
 * Example:
 *   agent.use(requestIdMiddleware());
 *
 *   // Access request ID in skill
 *   agent.skill('test', async (params, { metadata }) => {
 *     console.log(`Request ID: ${metadata.requestId}`);
 *   });
 */
export function requestIdMiddleware(options?: {
  headerName?: string;
  generator?: () => string;
}): Middleware {
  const { headerName = 'X-Request-ID', generator = generateId } = options ?? {};

  return async (ctx: MiddlewareContext, next: MiddlewareNext) => {
    const requestId = ctx.metadata[headerName.toLowerCase()] ?? generator();
    ctx.metadata.requestId = requestId;
    return await next();
  };
}

/**
 * Generate a unique ID.
 */
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

/**
 * CORS middleware (for Express integration).
 *
 * This is already handled by Agent.corsOrigins, but you can use this
 * for more granular control.
 *
 * Example:
 *   agent.use(corsMiddleware({
 *     origins: ['https://example.com'],
 *     methods: ['GET', 'POST'],
 *   }));
 */
export function corsMiddleware(options: {
  origins: string[];
  methods?: string[];
  headers?: string[];
}): Middleware {
  const { origins, methods = ['GET', 'POST', 'OPTIONS'], headers = [] } = options;

  return async (ctx: MiddlewareContext, next: MiddlewareNext) => {
    // Store CORS info in metadata for the HTTP layer to use
    ctx.metadata.cors = {
      origins,
      methods,
      headers,
    };
    return await next();
  };
}
