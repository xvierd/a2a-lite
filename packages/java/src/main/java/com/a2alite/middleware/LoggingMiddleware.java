package com.a2alite.middleware;

import com.a2alite.Middleware;
import com.a2alite.MiddlewareContext;
import com.a2alite.MiddlewareNext;

import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Logging middleware - logs skill calls and their results.
 *
 * <pre>{@code
 * agent.use(LoggingMiddleware.create());
 * }</pre>
 */
public class LoggingMiddleware {
    private LoggingMiddleware() {}

    /**
     * Create a logging middleware with default logger.
     */
    public static Middleware create() {
        return create(Logger.getLogger("a2a-lite"));
    }

    /**
     * Create a logging middleware with a custom logger.
     */
    public static Middleware create(Logger logger) {
        return (MiddlewareContext ctx, MiddlewareNext next) -> {
            long start = System.currentTimeMillis();
            logger.info("Calling skill: " + ctx.skill());

            try {
                Object result = next.call();
                long elapsed = System.currentTimeMillis() - start;
                logger.info("Skill " + ctx.skill() + " completed in " + elapsed + "ms");
                return result;
            } catch (Exception e) {
                long elapsed = System.currentTimeMillis() - start;
                logger.log(Level.SEVERE,
                    "Skill " + ctx.skill() + " failed after " + elapsed + "ms: " + e.getMessage());
                throw e;
            }
        };
    }
}
