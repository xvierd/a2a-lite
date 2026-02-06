package com.a2alite;

/**
 * Middleware function for processing requests.
 *
 * <pre>{@code
 * agent.use((ctx, next) -> {
 *     System.out.println("Calling: " + ctx.skill());
 *     Object result = next.call();
 *     System.out.println("Result: " + result);
 *     return result;
 * });
 * }</pre>
 */
@FunctionalInterface
public interface Middleware {
    /**
     * Apply the middleware.
     *
     * @param ctx The middleware context
     * @param next The next handler in the chain
     * @return The result
     * @throws Exception if an error occurs
     */
    Object apply(MiddlewareContext ctx, MiddlewareNext next) throws Exception;
}
