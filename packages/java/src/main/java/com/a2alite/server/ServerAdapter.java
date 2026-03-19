package com.a2alite.server;

import com.a2alite.Agent;

/**
 * Strategy interface for HTTP server integrations.
 *
 * <p>Implement this interface to plug any HTTP server framework into an A2A Lite
 * {@link Agent}. The SDK ships with {@link JavalinServerAdapter} for Javalin;
 * users on Quarkus, Spring Boot, or other frameworks supply their own adapter.
 *
 * <p>Example — minimal custom adapter:
 * <pre>{@code
 * public class SpringServerAdapter implements ServerAdapter {
 *     private final int port;
 *     SpringServerAdapter(int port) { this.port = port; }
 *
 *     @Override public void start(Agent agent, int ignored) {
 *         SpringApplication.run(AgentSpringConfig.class);
 *     }
 *     @Override public void stop() { /* Spring manages lifecycle *\/ }
 * }
 * }</pre>
 */
public interface ServerAdapter {
    /**
     * Start the HTTP server and register all A2A Lite endpoints.
     *
     * <p>The server binds to all interfaces ({@code 0.0.0.0}) by default.
     * Override {@link #start(Agent, String, int)} for explicit host binding.
     *
     * @param agent the agent whose skills will be served
     * @param port  the port to listen on
     */
    default void start(Agent agent, int port) {
        start(agent, "0.0.0.0", port);
    }

    /**
     * Start the HTTP server on a specific host and port.
     *
     * <p>The default implementation delegates to {@link #start(Agent, int)},
     * ignoring the host. Implementations that support host binding should
     * override this method.
     *
     * @param agent the agent whose skills will be served
     * @param host  the host/address to bind to
     * @param port  the port to listen on
     */
    void start(Agent agent, String host, int port);

    /**
     * Stop the HTTP server and release resources.
     */
    void stop();
}
