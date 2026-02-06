package com.a2alite;

import com.a2alite.auth.AuthProvider;
import com.a2alite.auth.NoAuth;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import io.a2a.server.agentexecution.AgentExecutor;
import io.a2a.spec.AgentCapabilities;
import io.a2a.spec.AgentCard;
import io.a2a.spec.AgentSkill;

import java.util.*;
import java.util.function.BiConsumer;
import java.util.function.Function;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Core Agent class - the heart of A2A Lite.
 *
 * Wraps the official A2A Java SDK with a simple, intuitive API.
 *
 * <pre>{@code
 * var agent = Agent.builder()
 *     .name("Bot")
 *     .description("My bot")
 *     .build();
 *
 * agent.skill("greet", params -> "Hello, " + params.get("name") + "!");
 *
 * agent.run();
 * }</pre>
 */
public class Agent {
    private static final Logger LOGGER = Logger.getLogger(Agent.class.getName());

    private final String name;
    private final String description;
    private final String version;
    private final String url;
    private final AuthProvider auth;
    private final List<String> corsOrigins;
    private final boolean production;

    private final Map<String, SkillDefinition> skills = new LinkedHashMap<>();
    private final List<Middleware> middlewares = new ArrayList<>();
    private final List<Runnable> startupHooks = new ArrayList<>();
    private final List<Runnable> shutdownHooks = new ArrayList<>();
    private final List<BiConsumer<String, Object>> completeHooks = new ArrayList<>();
    private Function<Exception, Object> errorHandler;

    private final ObjectMapper mapper = new ObjectMapper();
    private boolean hasStreaming = false;

    private Agent(Builder builder) {
        this.name = builder.name;
        this.description = builder.description;
        this.version = builder.version != null ? builder.version : "1.0.0";
        this.url = builder.url;
        this.auth = builder.auth != null ? builder.auth : new NoAuth();
        this.corsOrigins = builder.corsOrigins;
        this.production = builder.production;
    }

    public static Builder builder() {
        return new Builder();
    }

    /**
     * Register a skill.
     */
    public Agent skill(String name, SkillHandler handler) {
        return skill(name, null, handler);
    }

    /**
     * Register a skill with configuration.
     */
    public Agent skill(String name, SkillConfig config, SkillHandler handler) {
        var def = new SkillDefinition(
            name,
            config != null && config.description() != null ? config.description() : "Skill: " + name,
            config != null && config.tags() != null ? config.tags() : List.of(),
            handler,
            config != null ? config.streaming() : false
        );

        if (def.isStreaming()) {
            hasStreaming = true;
        }

        skills.put(name, def);
        return this;
    }

    /**
     * Add middleware.
     */
    public Agent use(Middleware middleware) {
        middlewares.add(middleware);
        return this;
    }

    /**
     * Set error handler.
     */
    public Agent onError(Function<Exception, Object> handler) {
        this.errorHandler = handler;
        return this;
    }

    /**
     * Add startup hook.
     */
    public Agent onStartup(Runnable hook) {
        startupHooks.add(hook);
        return this;
    }

    /**
     * Add shutdown hook.
     */
    public Agent onShutdown(Runnable hook) {
        shutdownHooks.add(hook);
        return this;
    }

    /**
     * Add completion hook.
     */
    public Agent onComplete(BiConsumer<String, Object> hook) {
        completeHooks.add(hook);
        return this;
    }

    /**
     * Build the A2A-compliant Agent Card.
     */
    public AgentCard buildAgentCard(String host, int port) {
        var skillList = skills.values().stream()
            .map(s -> new AgentSkill.Builder()
                .id(s.name())
                .name(s.name())
                .description(s.description())
                .tags(s.tags())
                .build())
            .toList();

        var agentUrl = url != null ? url : "http://" + host + ":" + port;

        return new AgentCard.Builder()
            .name(name)
            .description(description)
            .version(version)
            .url(agentUrl)
            .protocolVersion("0.2.0")
            .capabilities(new AgentCapabilities.Builder()
                .streaming(hasStreaming)
                .pushNotifications(!completeHooks.isEmpty())
                .stateTransitionHistory(false)
                .build())
            .defaultInputModes(List.of("text"))
            .defaultOutputModes(List.of("text"))
            .skills(skillList)
            .build();
    }

    /**
     * Get the agent executor for use with the SDK.
     */
    public AgentExecutor getExecutor() {
        return new LiteAgentExecutor(skills, middlewares, completeHooks, auth);
    }

    /**
     * Build a JSON representation of the agent card.
     * Useful for standalone mode without the full SDK.
     */
    public ObjectNode buildAgentCardJson(String host, int port) {
        var card = mapper.createObjectNode();
        card.put("name", name);
        card.put("description", description);
        card.put("version", version);
        card.put("protocolVersion", "0.3.0");
        card.put("url", url != null ? url : "http://" + host + ":" + port);

        var capabilities = card.putObject("capabilities");
        capabilities.put("streaming", hasStreaming);
        capabilities.put("pushNotifications", !completeHooks.isEmpty());

        card.putArray("defaultInputModes").add("text");
        card.putArray("defaultOutputModes").add("text");

        var skillsArray = card.putArray("skills");
        for (var skill : skills.values()) {
            var s = skillsArray.addObject();
            s.put("id", skill.name());
            s.put("name", skill.name());
            s.put("description", skill.description());

            var tags = s.putArray("tags");
            for (var tag : skill.tags()) {
                tags.add(tag);
            }
        }

        return card;
    }

    /**
     * Handle an incoming message (for standalone mode).
     */
    public Object handleMessage(JsonNode message) throws Exception {
        // Extract text from message
        String text = "";
        var parts = message.path("parts");
        if (parts.isArray()) {
            for (var part : parts) {
                if ("text".equals(part.path("type").asText()) ||
                    "text".equals(part.path("kind").asText())) {
                    text = part.path("text").asText("");
                    break;
                }
            }
        }

        // Parse skill call
        String skillName = null;
        Map<String, Object> params = new HashMap<>();

        try {
            var parsed = mapper.readTree(text);
            if (parsed.has("skill")) {
                skillName = parsed.path("skill").asText();
                if (parsed.has("params")) {
                    params = mapper.convertValue(parsed.path("params"), Map.class);
                }
            }
        } catch (Exception e) {
            params.put("message", text);
        }

        // Build middleware context
        var ctx = new MiddlewareContext(skillName, params, text, new HashMap<>());

        // Execute through middleware chain
        final String finalSkillName = skillName;
        MiddlewareNext finalHandler = () -> executeSkill(finalSkillName, ctx.params());

        MiddlewareNext handler = finalHandler;
        for (int i = middlewares.size() - 1; i >= 0; i--) {
            var middleware = middlewares.get(i);
            var next = handler;
            handler = () -> middleware.apply(ctx, next);
        }

        Object result = handler.call();

        // Call completion hooks
        for (var hook : completeHooks) {
            try {
                hook.accept(finalSkillName, result);
            } catch (Exception e) {
                LOGGER.log(Level.WARNING, "Completion hook error for skill '" + finalSkillName + "'", e);
            }
        }

        return result;
    }

    /**
     * Execute a skill directly (for standalone mode).
     */
    private Object executeSkill(String skillName, Map<String, Object> params) throws Exception {
        // Default to first skill only if there's exactly one
        if (skillName == null || skillName.isEmpty()) {
            if (skills.isEmpty()) {
                return Map.of("error", "No skills registered");
            }
            if (skills.size() == 1) {
                skillName = skills.keySet().iterator().next();
            } else {
                return Map.of(
                    "error", "No skill specified. Use {\"skill\": \"name\", \"params\": {...}} format.",
                    "availableSkills", skills.keySet()
                );
            }
        }

        var skillDef = skills.get(skillName);
        if (skillDef == null) {
            return Map.of(
                "error", "Unknown skill: " + skillName,
                "availableSkills", skills.keySet()
            );
        }

        return skillDef.handler().handle(params);
    }

    /**
     * Run with Javalin (standalone mode - requires javalin dependency).
     * For Quarkus integration, use the agent card and executor producers instead.
     */
    public void run() {
        run(8787);
    }

    /**
     * Run with Javalin on a specific port.
     */
    public void run(int port) {
        run("0.0.0.0", port);
    }

    /**
     * Run with Javalin on specific host and port.
     */
    public void run(String host, int port) {
        // Production mode warning
        if (production) {
            String urlStr = url != null ? url : "http://" + host + ":" + port;
            if (!urlStr.startsWith("https://")) {
                LOGGER.warning("Running in production mode over HTTP. "
                    + "Consider using HTTPS for secure communication.");
            }
        }

        // Run startup hooks
        for (var hook : startupHooks) {
            hook.run();
        }

        try {
            // Use reflection to avoid compile-time dependency on Javalin
            var javalinClass = Class.forName("io.javalin.Javalin");
            var createMethod = javalinClass.getMethod("create");
            var app = createMethod.invoke(null);

            // Get handler types
            var handlerClass = Class.forName("io.javalin.http.Handler");

            // Agent card endpoint
            var getMethod = javalinClass.getMethod("get", String.class, handlerClass);
            var agentCardHandler = java.lang.reflect.Proxy.newProxyInstance(
                handlerClass.getClassLoader(),
                new Class[]{handlerClass},
                (proxy, method, args) -> {
                    if ("handle".equals(method.getName())) {
                        var ctx = args[0];
                        var jsonMethod = ctx.getClass().getMethod("json", Object.class);
                        jsonMethod.invoke(ctx, buildAgentCardJson(host, port));
                    }
                    return null;
                }
            );
            getMethod.invoke(app, "/.well-known/agent.json", agentCardHandler);

            // Main A2A endpoint
            var postMethod = javalinClass.getMethod("post", String.class, handlerClass);
            var messageHandler = java.lang.reflect.Proxy.newProxyInstance(
                handlerClass.getClassLoader(),
                new Class[]{handlerClass},
                (proxy, method, args) -> {
                    if ("handle".equals(method.getName())) {
                        var ctx = args[0];
                        handleRequest(ctx);
                    }
                    return null;
                }
            );
            postMethod.invoke(app, "/", messageHandler);

            // Start server
            var displayHost = "0.0.0.0".equals(host) ? "localhost" : host;

            System.out.printf("""
                ┌─────────────────────────────────────────────────┐
                │  🚀 A2A Lite Agent Started                      │
                ├─────────────────────────────────────────────────┤
                │  %s v%s
                │  %s
                │
                │  Skills:
                %s
                │
                │  Endpoints:
                │    • Agent Card: http://%s:%d/.well-known/agent.json
                │    • API: http://%s:%d/
                └─────────────────────────────────────────────────┘
                %n""",
                name, version,
                description,
                skills.values().stream()
                    .map(s -> "│    • " + s.name() + ": " + s.description())
                    .reduce((a, b) -> a + "\n" + b)
                    .orElse("│    (no skills)"),
                displayHost, port,
                displayHost, port
            );

            var startMethod = javalinClass.getMethod("start", String.class, int.class);
            startMethod.invoke(app, host, port);

            // Register shutdown hook
            Runtime.getRuntime().addShutdownHook(new Thread(() -> {
                for (var hook : shutdownHooks) {
                    hook.run();
                }
            }));

        } catch (ClassNotFoundException e) {
            throw new RuntimeException(
                "Javalin not found. Add 'io.javalin:javalin' dependency or use Quarkus integration.",
                e
            );
        } catch (Exception e) {
            throw new RuntimeException("Failed to start Javalin server", e);
        }
    }

    private void handleRequest(Object ctx) throws Exception {
        // Authenticate the request
        if (!(auth instanceof NoAuth)) {
            var headerMethod = ctx.getClass().getMethod("header", String.class);
            Map<String, String> headers = new HashMap<>();
            // Extract common auth headers via reflection on Javalin context
            try {
                var headerMapMethod = ctx.getClass().getMethod("headerMap");
                @SuppressWarnings("unchecked")
                Map<String, String> headerMap = (Map<String, String>) headerMapMethod.invoke(ctx);
                headers.putAll(headerMap);
            } catch (NoSuchMethodException e) {
                // Fallback: try individual headers
                String apiKey = (String) headerMethod.invoke(ctx, "X-API-Key");
                if (apiKey != null) headers.put("X-API-Key", apiKey);
                String authHeader = (String) headerMethod.invoke(ctx, "Authorization");
                if (authHeader != null) headers.put("Authorization", authHeader);
            }

            var authRequest = new com.a2alite.auth.AuthRequest(headers);
            var authResult = auth.authenticate(authRequest);
            if (!authResult.authenticated()) {
                var statusMethod = ctx.getClass().getMethod("status", int.class);
                var jsonMethod = ctx.getClass().getMethod("json", Object.class);
                statusMethod.invoke(ctx, 401);
                jsonMethod.invoke(ctx, Map.of(
                    "jsonrpc", "2.0",
                    "error", Map.of("code", -32600, "message", authResult.error() != null ? authResult.error() : "Authentication failed")
                ));
                return;
            }
        }

        var bodyMethod = ctx.getClass().getMethod("body");
        var jsonMethod = ctx.getClass().getMethod("json", Object.class);

        var body = mapper.readTree((String) bodyMethod.invoke(ctx));
        var method = body.path("method").asText();
        var id = body.path("id").asText();

        if ("message/send".equals(method)) {
            var message = body.path("params").path("message");
            var result = handleMessage(message);

            var response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.put("id", id);

            var resultNode = response.putObject("result");
            var partsArray = resultNode.putArray("parts");
            var textPart = partsArray.addObject();
            textPart.put("kind", "text");
            textPart.put("text", mapper.writeValueAsString(result));

            jsonMethod.invoke(ctx, response);
        } else {
            var response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.put("id", id);
            var error = response.putObject("error");
            error.put("code", -32601);
            error.put("message", "Method not found");
            jsonMethod.invoke(ctx, response);
        }
    }

    // Getters
    public String getName() { return name; }
    public String getDescription() { return description; }
    public String getVersion() { return version; }
    public AuthProvider getAuth() { return auth; }
    public Map<String, SkillDefinition> getSkills() { return Collections.unmodifiableMap(skills); }

    /**
     * Builder for Agent.
     */
    public static class Builder {
        private String name;
        private String description;
        private String version;
        private String url;
        private AuthProvider auth;
        private List<String> corsOrigins;
        private boolean production = false;

        public Builder name(String name) {
            this.name = name;
            return this;
        }

        public Builder description(String description) {
            this.description = description;
            return this;
        }

        public Builder version(String version) {
            this.version = version;
            return this;
        }

        public Builder url(String url) {
            this.url = url;
            return this;
        }

        public Builder auth(AuthProvider auth) {
            this.auth = auth;
            return this;
        }

        public Builder corsOrigins(List<String> corsOrigins) {
            this.corsOrigins = corsOrigins;
            return this;
        }

        public Builder production(boolean production) {
            this.production = production;
            return this;
        }

        public Agent build() {
            Objects.requireNonNull(name, "name is required");
            Objects.requireNonNull(description, "description is required");
            return new Agent(this);
        }
    }
}
