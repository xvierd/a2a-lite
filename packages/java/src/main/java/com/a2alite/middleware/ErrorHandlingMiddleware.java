package com.a2alite.middleware;

import com.a2alite.Middleware;
import com.a2alite.MiddlewareContext;
import com.a2alite.MiddlewareNext;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.function.BiFunction;

/**
 * Error handling middleware - catches exceptions and formats error responses.
 *
 * <pre>{@code
 * agent.use(ErrorHandlingMiddleware.create());
 *
 * // With custom error handler
 * agent.use(ErrorHandlingMiddleware.create((error, ctx) ->
 *     Map.of("error", error.getMessage())
 * ));
 * }</pre>
 */
public class ErrorHandlingMiddleware {
    private ErrorHandlingMiddleware() {}

    /**
     * Create with default error formatting.
     */
    public static Middleware create() {
        return create(false);
    }

    /**
     * Create with optional stack trace inclusion.
     */
    public static Middleware create(boolean includeStack) {
        return (MiddlewareContext ctx, MiddlewareNext next) -> {
            try {
                return next.call();
            } catch (Exception e) {
                var error = new LinkedHashMap<String, Object>();
                error.put("error", e.getMessage());
                error.put("type", e.getClass().getSimpleName());
                if (includeStack) {
                    var sw = new java.io.StringWriter();
                    e.printStackTrace(new java.io.PrintWriter(sw));
                    error.put("stack", sw.toString());
                }
                return error;
            }
        };
    }

    /**
     * Create with a custom error handler.
     */
    public static Middleware create(BiFunction<Exception, MiddlewareContext, Object> handler) {
        return (MiddlewareContext ctx, MiddlewareNext next) -> {
            try {
                return next.call();
            } catch (Exception e) {
                return handler.apply(e, ctx);
            }
        };
    }
}
