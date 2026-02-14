package com.a2alite.middleware;

import com.a2alite.Middleware;
import com.a2alite.MiddlewareContext;
import com.a2alite.MiddlewareNext;

/**
 * Timing middleware - adds execution time to metadata.
 *
 * <pre>{@code
 * agent.use(TimingMiddleware.create());
 * // After execution: ctx.metadata().get("executionTimeMs")
 * }</pre>
 */
public class TimingMiddleware {
    private TimingMiddleware() {}

    public static Middleware create() {
        return (MiddlewareContext ctx, MiddlewareNext next) -> {
            long start = System.currentTimeMillis();
            Object result = next.call();
            long elapsed = System.currentTimeMillis() - start;
            ctx.setMetadata("executionTimeMs", elapsed);
            return result;
        };
    }
}
