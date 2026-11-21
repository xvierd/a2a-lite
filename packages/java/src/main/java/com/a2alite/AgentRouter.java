package com.a2alite;

import com.a2alite.runtime.AgentRuntime;
import com.a2alite.server.JavalinServerAdapter;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.javalin.Javalin;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

/** Mount independent JSON-RPC agents on one Javalin listener. GET / lists their cards. */
public class AgentRouter implements AutoCloseable {
    private static final String CARD = "/.well-known/agent-card.json";
    private final Map<String, Agent> agents = new LinkedHashMap<>();
    private final List<AgentRuntime> runtimes = new ArrayList<>();
    private Javalin app;

    public synchronized AgentRouter mount(String prefix, Agent agent) {
        if (app != null) throw new IllegalStateException("Router already started");
        Objects.requireNonNull(agent, "agent");
        if (!prefix.startsWith("/")) prefix = "/" + prefix;
        if (prefix.endsWith("/")) prefix = prefix.substring(0, prefix.length() - 1);
        if (!prefix.isEmpty()) {
            for (String segment : prefix.substring(1).split("/", -1)) {
                if (!segment.matches("[A-Za-z0-9._~-]+") || segment.equals(".") || segment.equals(".."))
                    throw new IllegalArgumentException("Expected a literal mount path: " + prefix);
            }
        }
        if (agents.putIfAbsent(prefix, agent) != null) throw new IllegalArgumentException("Duplicate mount: " + prefix);
        return this;
    }

    private ObjectNode defaultCard(String host, int port) {
        String prefix = agents.containsKey("") ? "" : agents.keySet().iterator().next();
        return agents.get(prefix).buildAgentCardJson(host, port, prefix);
    }

    /** The root discovery card describes the root agent, or the first mount. */
    @Deprecated
    public Map<String, Object> buildMergedCard(String host, int port) {
        if (agents.isEmpty()) throw new IllegalStateException("Mount an agent before building its card");
        return new ObjectMapper().convertValue(defaultCard(host, port), new TypeReference<>() {});
    }

    public void run() { run("0.0.0.0", 8787); }
    public void run(int port) { run("0.0.0.0", port); }

    public void run(String host, int port) {
        start(host, port);
        Runtime.getRuntime().addShutdownHook(new Thread(this::close, "a2a-router-shutdown"));
    }

    /** Start an embedded router. Port zero selects an available port. */
    public synchronized AgentRouter start(String host, int port) {
        if (app != null) throw new IllegalStateException("Router already started");
        if (agents.isEmpty()) throw new IllegalStateException("Mount an agent before starting the router");
        String displayHost = "0.0.0.0".equals(host) ? "localhost" : host;
        try {
            app = Javalin.create(config -> {
                config.http.maxRequestSize = agents.values().stream()
                    .mapToInt(agent -> agent.getRuntimeOptions().limits().maxRequestBytes()).max().orElseThrow();
                var directory = agents.entrySet().stream().map(entry -> Map.of(
                    "name", entry.getValue().getName(), "card", entry.getKey() + CARD)).toList();
                config.routes.get("/", ctx -> ctx.json(Map.of("agents", directory)));
                if (!agents.containsKey("")) {
                    config.routes.get(CARD, ctx -> ctx.json(defaultCard(displayHost, port())));
                }
                agents.forEach((prefix, agent) -> {
                    var adapter = JavalinServerAdapter.mounted(config, prefix, agent.getCorsOrigins(), this::port);
                    runtimes.add(agent.start(host, port, adapter));
                });
            });
            app.start(host, port);
            return this;
        } catch (RuntimeException failure) {
            close();
            throw failure;
        }
    }

    public int port() { return app.port(); }

    @Override
    public synchronized void close() {
        RuntimeException failure = null;
        try {
            for (var runtime : runtimes) {
                try {
                    runtime.close();
                } catch (RuntimeException error) {
                    if (failure == null) failure = error;
                    else failure.addSuppressed(error);
                }
            }
            if (failure != null) throw failure;
        } finally {
            runtimes.clear();
            if (app != null) app.stop();
            app = null;
        }
    }
}
