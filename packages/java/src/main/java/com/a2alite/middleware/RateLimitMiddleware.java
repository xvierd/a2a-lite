package com.a2alite.middleware;

import com.a2alite.Middleware;
import com.a2alite.MiddlewareContext;
import com.a2alite.MiddlewareNext;

import java.util.concurrent.ConcurrentLinkedDeque;

/**
 * In-memory rate limiting middleware.
 *
 * <pre>{@code
 * agent.use(RateLimitMiddleware.create(60)); // 60 requests per minute
 * }</pre>
 */
public class RateLimitMiddleware {
    private RateLimitMiddleware() {}

    /**
     * Create a rate limiting middleware.
     *
     * @param requestsPerMinute Maximum requests per minute
     */
    public static Middleware create(int requestsPerMinute) {
        return create(requestsPerMinute, 60_000L);
    }

    /**
     * Create a rate limiting middleware with custom window.
     *
     * @param maxRequests Maximum requests per window
     * @param windowMs Window size in milliseconds
     */
    public static Middleware create(int maxRequests, long windowMs) {
        var requestTimes = new ConcurrentLinkedDeque<Long>();

        return (MiddlewareContext ctx, MiddlewareNext next) -> {
            long now = System.currentTimeMillis();
            long windowStart = now - windowMs;

            // Remove old entries
            while (!requestTimes.isEmpty() && requestTimes.peekFirst() < windowStart) {
                requestTimes.pollFirst();
            }

            if (requestTimes.size() >= maxRequests) {
                throw new RateLimitExceededException(
                    "Rate limit exceeded: " + maxRequests + " requests per " + (windowMs / 1000) + "s"
                );
            }

            requestTimes.addLast(now);
            return next.call();
        };
    }

    /**
     * Exception thrown when rate limit is exceeded.
     */
    public static class RateLimitExceededException extends RuntimeException {
        public RateLimitExceededException(String message) {
            super(message);
        }
    }
}
