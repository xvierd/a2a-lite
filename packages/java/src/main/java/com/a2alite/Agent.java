package com.a2alite;

import com.a2alite.auth.AuthProvider;
import com.a2alite.auth.NoAuth;
import com.a2alite.errors.A2ALiteException;
import com.a2alite.errors.SkillNotFoundException;
import com.a2alite.push.PushNotifier;
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
 * <p>Wraps the official A2A Java SDK with a simple, intuitive API.
 *
 * <p>For standalone HTTP serving, Javalin is used as an optional dependency
 * loaded via reflection. This avoids forcing Javalin as a hard compile-time
 * dependency — users who deploy on Quarkus or another container need not
 * include it. If Javalin is not on the classpath, calling {@link #run()} will
 * throw a {@link RuntimeException} with an actionable message. See
 * {@link #run(String, int)} for details.
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
    private static final String PROTOCOL_VERSION = "0.3.0";

    private final String name;
    private final String description;
    private final String version;
    private final String url;
    private final AuthProvider auth;
    private final List<String> corsOrigins;
    private final boolean production;

    private final AgentNetwork network;
    private final TaskStore taskStore;

    private final Map<String, SkillDefinition> skills = new LinkedHashMap<>();
    private final List<Middleware> middlewares = new ArrayList<>();
    private final List<Runnable> startupHooks = new ArrayList<>();
    private final List<Runnable> shutdownHooks = new ArrayList<>();
    private final List<BiConsumer<String, Object>> completeHooks = new ArrayList<>();
    private Function<Exception, Object> errorHandler;

    private final ObjectMapper mapper = new ObjectMapper();
    private boolean hasStreaming = false;
    private Thread shutdownHookThread;

    private Agent(Builder builder) {
        this.name = builder.name;
        this.description = builder.description;
        this.version = builder.version != null ? builder.version : "1.0.0";
        this.url = builder.url;
        this.auth = builder.auth != null ? builder.auth : new NoAuth();
        this.corsOrigins = builder.corsOrigins;
        this.production = builder.production;
        this.network = builder.network;
        this.taskStore = resolveTaskStore(builder);

        // Auto-register push notifier as a completion hook
        if (builder.pushNotifier != null) {
            final PushNotifier notifier = builder.pushNotifier;
            final String agentName = this.name;
            this.completeHooks.add(0, (skillName, result) -> {
                try {
                    java.util.Map<String, Object> event = new java.util.HashMap<>();
                    event.put("skill", skillName);
                    event.put("result", result);
                    event.put("status", "completed");
                    event.put("timestamp", System.currentTimeMillis());
                    event.put("agent", agentName);
                    notifier.notify(event);
                } catch (Exception e) {
                    LOGGER.warning("Push notifier error: " + e.getMessage());
                }
            });
        }
    }

    /**
     * Resolves the task store from the builder. If no store is explicitly
     * provided, an {@link InMemoryTaskStore} is used as the default.
     */
    private static TaskStore resolveTaskStore(Builder builder) {
        if (builder.taskStore != null) {
            return builder.taskStore;
        }
        return new InMemoryTaskStore();
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
     * Register a skill that receives a TaskContext for progress tracking.
     */
    public Agent skill(String name, SkillHandlerWithContext handler) {
        return skill(name, null, handler);
    }

    /**
     * Register a skill with configuration that receives a TaskContext.
     */
    public Agent skill(String name, SkillConfig config, SkillHandlerWithContext handler) {
        final TaskStore store = this.taskStore;
        SkillHandler wrappedHandler = params -> {
            var task = store.create(name, params);
            var context = new TaskContext(task);
            return handler.handle(params, context);
        };

        var def = new SkillDefinition(
            name,
            config != null && config.description() != null ? config.description() : "Skill: " + name,
            config != null && config.tags() != null ? config.tags() : List.of(),
            wrappedHandler,
            config != null ? config.streaming() : false,
            true
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
            .protocolVersion(PROTOCOL_VERSION)
            .capabilities(new AgentCapabilities.Builder()
                .streaming(hasStreaming)
                .pushNotifications(!completeHooks.isEmpty())
                .stateTransitionHistory(false)
                .build())
            .defaultInputModes(List.of("application/json"))
            .defaultOutputModes(List.of("application/json"))
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
        card.put("protocolVersion", PROTOCOL_VERSION);
        card.put("url", url != null ? url : "http://" + host + ":" + port);

        var capabilities = card.putObject("capabilities");
        capabilities.put("streaming", hasStreaming);
        capabilities.put("pushNotifications", !completeHooks.isEmpty());

        card.putArray("defaultInputModes").add("application/json");
        card.putArray("defaultOutputModes").add("application/json");

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
     * Handle an incoming message with auth (public entry point for standalone mode).
     */
    public Object handleMessage(JsonNode message, Map<String, String> headers) throws Exception {
        if (!(auth instanceof NoAuth)) {
            var authRequest = new com.a2alite.auth.AuthRequest(headers);
            var authResult = auth.authenticate(authRequest);
            if (!authResult.authenticated()) {
                throw new SecurityException(authResult.error() != null ? authResult.error() : "Authentication failed");
            }
        }
        return handleMessageInternal(message);
    }

    /**
     * Handle an incoming message (package-private, bypasses auth for testing).
     */
    Object handleMessage(JsonNode message) throws Exception {
        return handleMessageInternal(message);
    }

    private Object handleMessageInternal(JsonNode message) throws Exception {
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

        Object result;
        try {
            result = handler.call();
        } catch (A2ALiteException e) {
            if (errorHandler != null) {
                return errorHandler.apply(e);
            }
            return e.toResponse();
        }

        // Call completion hooks
        for (var hook : completeHooks) {
            try {
                String hookSkillName = finalSkillName != null ? finalSkillName : "(unknown)";
                hook.accept(hookSkillName, result);
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
                throw new SkillNotFoundException("", List.of());
            }
            if (skills.size() == 1) {
                skillName = skills.keySet().iterator().next();
            } else {
                throw new SkillNotFoundException("", new ArrayList<>(skills.keySet()));
            }
        }

        var skillDef = skills.get(skillName);
        if (skillDef == null) {
            throw new SkillNotFoundException(skillName, new ArrayList<>(skills.keySet()));
        }

        return skillDef.handler().handle(params);
    }

    /**
     * Run with Javalin (standalone mode).
     *
     * <p>Javalin is loaded via reflection so that it remains an optional
     * dependency. Users deploying on Quarkus or another container can omit
     * {@code io.javalin:javalin} from their classpath entirely and rely on the
     * framework's own HTTP layer instead. If Javalin is not present at runtime,
     * this method throws a {@link RuntimeException} with an actionable message.
     *
     * <p>For Quarkus integration, use the agent card and executor producers
     * instead of calling {@code run()}.
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
     *
     * <p>Javalin is an optional dependency loaded via reflection to avoid
     * forcing it as a hard dependency. If Javalin is not on the classpath,
     * the HTTP server features are unavailable and a {@link RuntimeException}
     * with a descriptive message is thrown.
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
            // Use reflection to avoid compile-time dependency on Javalin.
            // Javalin is declared compileOnly so that Quarkus users are not forced
            // to bundle it. At runtime it is available only when the user has added
            // the dependency explicitly.
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

            // OPTIONS preflight handler for CORS
            if (corsOrigins != null && !corsOrigins.isEmpty()) {
                var optionsMethod = javalinClass.getMethod("options", String.class, handlerClass);
                var optionsHandler = java.lang.reflect.Proxy.newProxyInstance(
                    handlerClass.getClassLoader(),
                    new Class[]{handlerClass},
                    (proxy, method, args) -> {
                        if ("handle".equals(method.getName())) {
                            var optCtx = args[0];
                            var hdrMethod = optCtx.getClass().getMethod("header", String.class, String.class);
                            hdrMethod.invoke(optCtx, "Access-Control-Allow-Origin", String.join(",", corsOrigins));
                            hdrMethod.invoke(optCtx, "Access-Control-Allow-Methods", "GET, POST, OPTIONS");
                            hdrMethod.invoke(optCtx, "Access-Control-Allow-Headers", "*");
                            var statusMethod = optCtx.getClass().getMethod("status", int.class);
                            statusMethod.invoke(optCtx, 204);
                        }
                        return null;
                    }
                );
                optionsMethod.invoke(app, "/", optionsHandler);
            }

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

            // Register shutdown hook (remove old one first to prevent accumulation)
            if (shutdownHookThread != null) {
                Runtime.getRuntime().removeShutdownHook(shutdownHookThread);
            }
            shutdownHookThread = new Thread(() -> {
                for (var hook : shutdownHooks) {
                    hook.run();
                }
            });
            Runtime.getRuntime().addShutdownHook(shutdownHookThread);

        } catch (ClassNotFoundException e) {
            throw new RuntimeException(
                "Javalin not found. Add 'io.javalin:javalin' dependency or use Quarkus integration.",
                e
            );
        } catch (Exception e) {
            throw new RuntimeException("Failed to start Javalin server", e);
        }
    }

    /**
     * Handles a single HTTP request received from the Javalin context (passed
     * as {@code Object} to avoid a compile-time dependency on Javalin).
     *
     * <p>The method is decomposed into focused private helpers:
     * <ol>
     *   <li>{@link #addCorsHeaders(Object)} — writes CORS response headers</li>
     *   <li>{@link #extractHeaders(Object)} — reads request headers via reflection</li>
     *   <li>{@link #authenticateRequest(Object, Map)} — validates auth and writes a 401 on failure</li>
     *   <li>{@link #parseJsonRpcBody(Object)} — deserializes the JSON-RPC request body</li>
     * </ol>
     */
    private void handleRequest(Object ctx) throws Exception {
        addCorsHeaders(ctx);

        Map<String, String> headers = extractHeaders(ctx);
        if (!authenticateRequest(ctx, headers)) {
            return; // response already written
        }

        JsonNode body = parseJsonRpcBody(ctx);
        var method = body.path("method").asText();
        var id = body.path("id").asText();
        var jsonMethod = ctx.getClass().getMethod("json", Object.class);

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

    /**
     * Writes CORS headers to the response if CORS origins are configured.
     *
     * @param ctx the Javalin context (as {@code Object} due to optional dependency)
     */
    private void addCorsHeaders(Object ctx) throws Exception {
        if (corsOrigins != null && !corsOrigins.isEmpty()) {
            var headerMethod = ctx.getClass().getMethod("header", String.class, String.class);
            headerMethod.invoke(ctx, "Access-Control-Allow-Origin", String.join(",", corsOrigins));
            headerMethod.invoke(ctx, "Access-Control-Allow-Methods", "GET, POST, OPTIONS");
            headerMethod.invoke(ctx, "Access-Control-Allow-Headers", "*");
        }
    }

    /**
     * Extracts all HTTP request headers from the Javalin context via reflection.
     *
     * <p>Falls back to extracting only common auth headers when the full header
     * map is unavailable on the context type.
     *
     * @param ctx the Javalin context (as {@code Object} due to optional dependency)
     * @return a mutable map of header name to header value
     */
    private Map<String, String> extractHeaders(Object ctx) throws Exception {
        Map<String, String> headers = new HashMap<>();
        try {
            var headerMapMethod = ctx.getClass().getMethod("headerMap");
            @SuppressWarnings("unchecked")
            Map<String, String> headerMap = (Map<String, String>) headerMapMethod.invoke(ctx);
            headers.putAll(headerMap);
        } catch (NoSuchMethodException e) {
            // Fallback: extract only the headers relevant to authentication
            var headerMethod = ctx.getClass().getMethod("header", String.class);
            String apiKey = (String) headerMethod.invoke(ctx, "X-API-Key");
            if (apiKey != null) headers.put("X-API-Key", apiKey);
            String authHeader = (String) headerMethod.invoke(ctx, "Authorization");
            if (authHeader != null) headers.put("Authorization", authHeader);
        }
        return headers;
    }

    /**
     * Authenticates the request using the configured {@link AuthProvider}.
     *
     * <p>If authentication fails, writes a {@code 401} JSON-RPC error response
     * and returns {@code false} so the caller can short-circuit.
     *
     * @param ctx     the Javalin context (as {@code Object} due to optional dependency)
     * @param headers the headers extracted by {@link #extractHeaders(Object)}
     * @return {@code true} if the request is authenticated (or auth is disabled),
     *         {@code false} if a 401 was sent
     */
    private boolean authenticateRequest(Object ctx, Map<String, String> headers) throws Exception {
        if (auth instanceof NoAuth) {
            return true;
        }

        var authRequest = new com.a2alite.auth.AuthRequest(headers);
        var authResult = auth.authenticate(authRequest);
        if (!authResult.authenticated()) {
            var statusMethod = ctx.getClass().getMethod("status", int.class);
            var jsonMethod = ctx.getClass().getMethod("json", Object.class);
            statusMethod.invoke(ctx, 401);
            jsonMethod.invoke(ctx, Map.of(
                "jsonrpc", "2.0",
                "error", Map.of(
                    "code", -32600,
                    "message", authResult.error() != null ? authResult.error() : "Authentication failed"
                )
            ));
            return false;
        }
        return true;
    }

    /**
     * Reads and deserializes the JSON-RPC request body.
     *
     * @param ctx the Javalin context (as {@code Object} due to optional dependency)
     * @return the parsed {@link JsonNode} body
     */
    private JsonNode parseJsonRpcBody(Object ctx) throws Exception {
        var bodyMethod = ctx.getClass().getMethod("bodyAsBytes");
        return mapper.readTree((byte[]) bodyMethod.invoke(ctx));
    }

    /**
     * Delegate a skill call to a remote agent.
     *
     * The target can be a full URL or a name registered in this agent's network.
     */
    public Object delegate(String target, String skill, Map<String, Object> params) throws Exception {
        return delegate(target, skill, params, 30);
    }

    public Object delegate(String target, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        String url = target;
        if (network != null && !target.startsWith("http://") && !target.startsWith("https://")) {
            var resolved = network.get(target);
            if (resolved.isEmpty()) {
                throw new IllegalArgumentException(
                    "Agent '" + target + "' not found in network. Available: " + network.list().keySet()
                );
            }
            url = resolved.get();
        }
        if (network == null && !target.startsWith("http://") && !target.startsWith("https://")) {
            throw new IllegalArgumentException("No network configured and target is not a URL: " + target);
        }
        return new AgentNetwork().callRemoteSkill(url, skill, params, timeoutSeconds);
    }

    /**
     * Return skills as OpenAI-compatible tool schemas for use with LLM APIs.
     *
     * <pre>{@code
     * var tools = agent.getToolSchemas();
     * // tools is a List of Maps in OpenAI function-calling format
     * }</pre>
     *
     * @return List of tool schema maps in OpenAI format.
     */
    public List<Map<String, Object>> getToolSchemas() {
        var schemas = new ArrayList<Map<String, Object>>();
        for (var skillDef : skills.values()) {
            var function = new HashMap<String, Object>();
            function.put("name", skillDef.name());
            function.put("description", skillDef.description());
            function.put("parameters", Map.of("type", "object", "properties", Map.of()));

            var tool = new HashMap<String, Object>();
            tool.put("type", "function");
            tool.put("function", function);
            schemas.add(tool);
        }
        return schemas;
    }

    // Getters
    public String getName() { return name; }
    public String getDescription() { return description; }
    public String getVersion() { return version; }
    public AuthProvider getAuth() { return auth; }
    public Map<String, SkillDefinition> getSkills() { return Collections.unmodifiableMap(skills); }
    public AgentNetwork getNetwork() { return network; }
    public TaskStore getTaskStore() { return taskStore; }

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
        private AgentNetwork network;
        private TaskStore taskStore;
        private PushNotifier pushNotifier;

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

        public Builder network(AgentNetwork network) {
            this.network = network;
            return this;
        }

        public Builder taskStore(TaskStore taskStore) {
            this.taskStore = taskStore;
            return this;
        }

        public Builder pushNotifier(PushNotifier pushNotifier) {
            this.pushNotifier = pushNotifier;
            return this;
        }

        public Agent build() {
            Objects.requireNonNull(name, "name is required");
            Objects.requireNonNull(description, "description is required");
            return new Agent(this);
        }
    }
}
