package com.a2alite.middleware;

import com.a2alite.Middleware;
import com.a2alite.MiddlewareContext;
import com.a2alite.MiddlewareNext;

import java.util.List;
import java.util.Map;

/**
 * CORS middleware - stores CORS configuration in metadata for the HTTP layer.
 *
 * <pre>{@code
 * agent.use(CorsMiddleware.create(List.of("https://example.com")));
 * }</pre>
 */
public class CorsMiddleware {
    private CorsMiddleware() {}

    /**
     * Create CORS middleware with allowed origins.
     */
    public static Middleware create(List<String> origins) {
        return create(origins, List.of("GET", "POST", "OPTIONS"), List.of());
    }

    /**
     * Create CORS middleware with full configuration.
     */
    public static Middleware create(List<String> origins, List<String> methods, List<String> headers) {
        return (MiddlewareContext ctx, MiddlewareNext next) -> {
            ctx.setMetadata("cors", Map.of(
                "origins", origins,
                "methods", methods,
                "headers", headers
            ));
            return next.call();
        };
    }
}
