package com.a2alite.middleware;

import com.a2alite.Middleware;
import com.a2alite.MiddlewareContext;
import com.a2alite.MiddlewareNext;

/**
 * Request ID middleware - adds unique request ID to metadata.
 *
 * <pre>{@code
 * agent.use(RequestIdMiddleware.create());
 * // After: ctx.metadata().get("requestId")
 * }</pre>
 */
public class RequestIdMiddleware {
    private RequestIdMiddleware() {}

    public static Middleware create() {
        return (MiddlewareContext ctx, MiddlewareNext next) -> {
            String requestId = System.currentTimeMillis() + "-" +
                Long.toString(Math.abs(java.util.concurrent.ThreadLocalRandom.current().nextLong()), 36).substring(0, 7);
            ctx.setMetadata("requestId", requestId);
            return next.call();
        };
    }
}
