package com.a2alite;

/**
 * The next handler in the middleware chain.
 */
@FunctionalInterface
public interface MiddlewareNext {
    /**
     * Call the next handler.
     *
     * @return The result
     * @throws Exception if an error occurs
     */
    Object call() throws Exception;
}
