package com.a2alite.server;

import com.a2alite.Agent;
import com.a2alite.auth.AuthProvider;
import com.a2alite.auth.NoAuth;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import io.javalin.Javalin;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * {@link ServerAdapter} implementation backed by Javalin.
 *
 * <p>This is the default adapter used when Javalin is on the classpath. It
 * registers the A2A Lite endpoints ({@code GET /.well-known/agent.json} and
 * {@code POST /}) on a Javalin instance and starts the HTTP server.
 *
 * <p>Javalin is declared {@code compileOnly} in the SDK's build file so that
 * users who deploy on Quarkus, Spring Boot, or another container are not
 * forced to bundle it. If Javalin is absent at runtime the static factory
 * method {@link #createIfAvailable()} returns {@code null} instead of
 * throwing, allowing {@link Agent} to produce a helpful error message.
 */
public class JavalinServerAdapter implements ServerAdapter {

    private final List<String> corsOrigins;
    private final ObjectMapper mapper;

    private Javalin app;

    /**
     * Creates a new adapter with no CORS configuration.
     */
    public JavalinServerAdapter() {
        this(null);
    }

    /**
     * Creates a new adapter with the given CORS origins.
     *
     * @param corsOrigins allowed CORS origins, or {@code null} / empty to disable CORS headers
     */
    public JavalinServerAdapter(List<String> corsOrigins) {
        this.corsOrigins = corsOrigins;
        this.mapper = new ObjectMapper();
    }

    /**
     * Attempts to create a {@link JavalinServerAdapter} without throwing if
     * Javalin is absent from the classpath.
     *
     * <p>This method is used by {@link Agent} to provide automatic default
     * behaviour: if Javalin is available a ready-to-use adapter is returned;
     * otherwise {@code null} is returned so the caller can decide how to
     * handle the missing dependency.
     *
     * @return a new {@link JavalinServerAdapter}, or {@code null} if Javalin
     *         is not on the classpath
     */
    public static JavalinServerAdapter createIfAvailable() {
        try {
            Class.forName("io.javalin.Javalin");
            return new JavalinServerAdapter();
        } catch (ClassNotFoundException e) {
            return null;
        }
    }

    /**
     * Same as {@link #createIfAvailable()} but also forwards the CORS origins
     * from the agent builder so the adapter is fully configured.
     */
    public static JavalinServerAdapter createIfAvailable(List<String> corsOrigins) {
        try {
            Class.forName("io.javalin.Javalin");
            return new JavalinServerAdapter(corsOrigins);
        } catch (ClassNotFoundException e) {
            return null;
        }
    }

    @Override
    public void start(Agent agent, String host, int port) {
        this.app = Javalin.create();

        // Agent card endpoint
        app.get("/.well-known/agent.json", ctx -> {
            ctx.json(agent.buildAgentCardJson(host, port));
        });

        // Main A2A JSON-RPC endpoint
        app.post("/", ctx -> handleRequest(ctx, agent));

        // OPTIONS preflight handler for CORS
        if (corsOrigins != null && !corsOrigins.isEmpty()) {
            app.options("/", ctx -> {
                ctx.header("Access-Control-Allow-Origin", String.join(",", corsOrigins));
                ctx.header("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
                ctx.header("Access-Control-Allow-Headers", "*");
                ctx.status(204);
            });
        }

        var displayHost = "0.0.0.0".equals(host) ? "localhost" : host;

        System.out.printf("""
            \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510
            \u2502  \uD83D\uDE80 A2A Lite Agent Started                      \u2502
            \u251c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2524
            \u2502  %s v%s
            \u2502  %s
            \u2502
            \u2502  Skills:
            %s
            \u2502
            \u2502  Endpoints:
            \u2502    \u2022 Agent Card: http://%s:%d/.well-known/agent.json
            \u2502    \u2022 API: http://%s:%d/
            \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518
            %n""",
            agent.getName(), agent.getVersion(),
            agent.getDescription(),
            agent.getSkills().values().stream()
                .map(s -> "\u2502    \u2022 " + s.name() + ": " + s.description())
                .reduce((a, b) -> a + "\n" + b)
                .orElse("\u2502    (no skills)"),
            displayHost, port,
            displayHost, port
        );

        app.start(host, port);
    }

    @Override
    public void stop() {
        if (app != null) {
            app.stop();
        }
    }

    // -----------------------------------------------------------------------
    // Request handling
    // -----------------------------------------------------------------------

    private void handleRequest(io.javalin.http.Context ctx, Agent agent) throws Exception {
        addCorsHeaders(ctx);

        Map<String, String> headers = new HashMap<>(ctx.headerMap());
        AuthProvider auth = agent.getAuth();

        if (!(auth instanceof NoAuth)) {
            var authReq = new com.a2alite.auth.AuthRequest(headers);
            var authResult = auth.authenticate(authReq);
            if (!authResult.authenticated()) {
                ctx.status(401);
                ctx.json(Map.of(
                    "jsonrpc", "2.0",
                    "error", Map.of(
                        "code", -32600,
                        "message", authResult.error() != null ? authResult.error() : "Authentication failed"
                    )
                ));
                return;
            }
        }

        JsonNode body = mapper.readTree(ctx.bodyAsBytes());
        var method = body.path("method").asText();
        var id = body.path("id").asText();

        if ("message/send".equals(method)) {
            var message = body.path("params").path("message");
            var result = agent.handleMessage(message, headers);

            var response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.put("id", id);

            var resultNode = response.putObject("result");
            var partsArray = resultNode.putArray("parts");
            var textPart = partsArray.addObject();
            textPart.put("kind", "text");
            textPart.put("text", mapper.writeValueAsString(result));

            ctx.json(response);
        } else if ("tasks/pushNotification/set".equals(method)) {
            handlePushNotificationSet(ctx, body, id, agent);
        } else if ("tasks/pushNotification/get".equals(method)) {
            handlePushNotificationGet(ctx, body, id, agent);
        } else if ("tasks/pushNotification/delete".equals(method)) {
            handlePushNotificationDelete(ctx, body, id, agent);
        } else {
            var response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.put("id", id);
            var error = response.putObject("error");
            error.put("code", -32601);
            error.put("message", "Method not found");
            ctx.json(response);
        }
    }

    @SuppressWarnings("unchecked")
    private void handlePushNotificationSet(io.javalin.http.Context ctx, JsonNode body, String id, Agent agent) throws Exception {
        var params = body.path("params");
        var taskId = params.has("id") ? params.path("id").asText() : params.path("taskId").asText();
        var configNode = params.path("pushNotificationConfig");
        var url = configNode.path("url").asText();
        var token = configNode.has("token") && !configNode.path("token").isNull()
                ? configNode.path("token").asText() : null;

        agent.getPushRegistry().set(taskId, url, token);

        var response = mapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.put("id", id);
        var result = response.putObject("result");
        result.put("id", taskId);
        var pushConfig = result.putObject("pushNotificationConfig");
        pushConfig.put("url", url);
        if (token != null) {
            pushConfig.put("token", token);
        }
        ctx.json(response);
    }

    private void handlePushNotificationGet(io.javalin.http.Context ctx, JsonNode body, String id, Agent agent) throws Exception {
        var params = body.path("params");
        var taskId = params.has("id") ? params.path("id").asText() : params.path("taskId").asText();

        var config = agent.getPushRegistry().get(taskId);

        var response = mapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.put("id", id);

        if (config.isPresent()) {
            var result = response.putObject("result");
            result.put("id", taskId);
            var pushConfig = result.putObject("pushNotificationConfig");
            pushConfig.put("url", config.get().url());
            if (config.get().token() != null) {
                pushConfig.put("token", config.get().token());
            }
        } else {
            var error = response.putObject("error");
            error.put("code", -32602);
            error.put("message", "No push notification config found for task: " + taskId);
        }

        ctx.json(response);
    }

    private void handlePushNotificationDelete(io.javalin.http.Context ctx, JsonNode body, String id, Agent agent) throws Exception {
        var params = body.path("params");
        var taskId = params.has("id") ? params.path("id").asText() : params.path("taskId").asText();

        boolean removed = agent.getPushRegistry().delete(taskId);

        var response = mapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.put("id", id);
        var result = response.putObject("result");
        result.put("id", taskId);
        result.put("deleted", removed);
        ctx.json(response);
    }

    private void addCorsHeaders(io.javalin.http.Context ctx) {
        if (corsOrigins != null && !corsOrigins.isEmpty()) {
            ctx.header("Access-Control-Allow-Origin", String.join(",", corsOrigins));
            ctx.header("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
            ctx.header("Access-Control-Allow-Headers", "*");
        }
    }
}
