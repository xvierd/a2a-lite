package com.a2alite;

import com.a2alite.auth.AuthProvider;
import com.a2alite.auth.NoAuth;
import com.a2alite.errors.A2ALiteException;
import com.a2alite.errors.SkillNotFoundException;
import com.a2alite.push.PushNotifier;
import com.a2alite.push.TaskPushRegistry;
import com.a2alite.server.JavalinServerAdapter;
import com.a2alite.server.ServerAdapter;
import com.a2alite.streaming.StreamingHandler;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.a2aproject.sdk.server.agentexecution.AgentExecutor;
import org.a2aproject.sdk.spec.AgentCapabilities;
import org.a2aproject.sdk.spec.AgentCard;
import org.a2aproject.sdk.spec.AgentInterface;
import org.a2aproject.sdk.spec.AgentSkill;

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
 * <p>For standalone HTTP serving, a {@link com.a2alite.server.ServerAdapter} is
 * used as a pluggable strategy. The default adapter is
 * {@link com.a2alite.server.JavalinServerAdapter}, which requires
 * {@code io.javalin:javalin} on the classpath. Users on Quarkus, Spring Boot,
 * or another framework can supply a custom adapter via
 * {@link Builder#serverAdapter(ServerAdapter)}.
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
    private static final String PROTOCOL_VERSION = "1.0";

    private final String name;
    private final String description;
    private final String version;
    private final String url;
    private final AuthProvider auth;
    private final List<String> corsOrigins;
    private final boolean production;

    private final AgentNetwork network;
    private final TaskStore taskStore;
    private final TaskPushRegistry pushRegistry = new TaskPushRegistry();

    private final Map<String, SkillDefinition> skills = new LinkedHashMap<>();
    private final List<Middleware> middlewares = new ArrayList<>();
    private final List<Runnable> startupHooks = new ArrayList<>();
    private final List<Runnable> shutdownHooks = new ArrayList<>();
    private final List<BiConsumer<String, Object>> completeHooks = new ArrayList<>();
    private Function<Exception, Object> errorHandler;

    private final ObjectMapper mapper = new ObjectMapper();
    private boolean hasStreaming = false;
    private Thread shutdownHookThread;
    private ServerAdapter serverAdapter;

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
        this.serverAdapter = builder.serverAdapter;

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
     * Build the A2A-compliant Agent Card (protocol v1.0).
     */
    public AgentCard buildAgentCard(String host, int port) {
        var skillList = skills.values().stream()
            .map(s -> AgentSkill.builder()
                .id(s.name())
                .name(s.name())
                .description(s.description())
                .tags(s.tags())
                .build())
            .toList();

        var agentUrl = url != null ? url : "http://" + host + ":" + port;

        return AgentCard.builder()
            .name(name)
            .description(description)
            .version(version)
            .supportedInterfaces(List.of(
                new AgentInterface("JSONRPC", agentUrl, null, PROTOCOL_VERSION),
                new AgentInterface("HTTP+JSON", agentUrl, null, PROTOCOL_VERSION)))
            .capabilities(AgentCapabilities.builder()
                .streaming(hasStreaming)
                .pushNotifications(!completeHooks.isEmpty())
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
        return new LiteAgentExecutor(skills, middlewares, completeHooks, auth, pushRegistry);
    }

    /**
     * Build a JSON representation of the agent card (A2A protocol v1.0).
     * Useful for standalone mode without the full SDK.
     */
    public ObjectNode buildAgentCardJson(String host, int port) {
        var agentUrl = url != null ? url : "http://" + host + ":" + port;

        var card = mapper.createObjectNode();
        card.put("name", name);
        card.put("description", description);
        card.put("version", version);

        var interfaces = card.putArray("supportedInterfaces");
        for (var binding : List.of("JSONRPC", "HTTP+JSON")) {
            var iface = interfaces.addObject();
            iface.put("protocolBinding", binding);
            iface.put("url", agentUrl);
            iface.put("protocolVersion", PROTOCOL_VERSION);
        }

        var capabilities = card.putObject("capabilities");
        capabilities.put("streaming", hasStreaming);
        capabilities.put("pushNotifications", !completeHooks.isEmpty());

        // Advertise the security scheme when an auth provider is configured
        var scheme = auth != null ? auth.getScheme() : Map.<String, Object>of();
        if (scheme != null && !scheme.isEmpty()) {
            var securitySchemes = card.putObject("securitySchemes");
            var securityRequirements = card.putArray("securityRequirements");
            addSecurityScheme(securitySchemes, securityRequirements, scheme);
        }

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
     * Adds the auth provider's scheme to the card's {@code securitySchemes} map
     * using the A2A v1.0 (proto3 JSON) oneof-keyed shape, plus a matching entry
     * in {@code securityRequirements}. Unknown scheme types are skipped.
     */
    @SuppressWarnings("unchecked")
    private void addSecurityScheme(ObjectNode securitySchemes,
                                   com.fasterxml.jackson.databind.node.ArrayNode securityRequirements,
                                   Map<String, Object> scheme) {
        var schemeType = Objects.toString(scheme.get("type"), "");
        String name;
        ObjectNode schemeNode = mapper.createObjectNode();

        switch (schemeType) {
            case "apiKey" -> {
                name = "apiKey";
                var apiKey = schemeNode.putObject("apiKeySecurityScheme");
                apiKey.put("name", Objects.toString(scheme.get("name"), "X-API-Key"));
                apiKey.put("location", Objects.toString(scheme.get("in"), "header"));
            }
            case "http" -> {
                var httpScheme = Objects.toString(scheme.get("scheme"), "bearer");
                name = httpScheme;
                var http = schemeNode.putObject("httpAuthSecurityScheme");
                http.put("scheme", httpScheme);
            }
            case "oauth2" -> {
                name = "oauth2";
                var oauth2 = schemeNode.putObject("oauth2SecurityScheme");
                var flows = oauth2.putObject("flows");
                var flowsMap = scheme.get("flows") instanceof Map<?, ?> f ? (Map<String, Object>) f : Map.<String, Object>of();
                var authCodeMap = flowsMap.get("authorizationCode") instanceof Map<?, ?> a ? (Map<String, Object>) a : Map.<String, Object>of();
                var authCode = flows.putObject("authorizationCode");
                authCode.put("authorizationUrl", Objects.toString(authCodeMap.get("authorizationUrl"), ""));
                authCode.put("tokenUrl", Objects.toString(authCodeMap.get("tokenUrl"), ""));
                authCode.put("refreshUrl", Objects.toString(authCodeMap.get("refreshUrl"), ""));
                var scopes = authCode.putObject("scopes");
                if (authCodeMap.get("scopes") instanceof Map<?, ?> scopesMap) {
                    scopesMap.forEach((k, v) -> scopes.put(Objects.toString(k), Objects.toString(v)));
                }
            }
            default -> {
                LOGGER.warning("Unknown auth scheme type '" + schemeType + "'; skipping agent card security schemes");
                return;
            }
        }

        securitySchemes.set(name, schemeNode);
        var requirement = securityRequirements.addObject();
        var requirementSchemes = requirement.putObject("schemes");
        requirementSchemes.putObject(name).putArray("list");
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
        // Extract text from message (A2A v1.0: text parts are {"text": ...})
        String text = "";
        var parts = message.path("parts");
        if (parts.isArray()) {
            for (var part : parts) {
                if (part.has("text")) {
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
     * Run with the configured server adapter (standalone mode) on the default port 8787.
     */
    public void run() {
        run(8787);
    }

    /**
     * Run with the configured server adapter on a specific port.
     */
    public void run(int port) {
        run("0.0.0.0", port);
    }

    /**
     * Run with the configured server adapter on the given host and port.
     *
     * <p>If no {@link ServerAdapter} was provided via {@link Builder#serverAdapter},
     * a {@link JavalinServerAdapter} is created automatically (requires
     * {@code io.javalin:javalin} on the classpath). If Javalin is absent and no
     * adapter was supplied, a {@link RuntimeException} with an actionable message
     * is thrown.
     */
    public void run(String host, int port) {
        if (production) {
            String urlStr = url != null ? url : "http://" + host + ":" + port;
            if (!urlStr.startsWith("https://")) {
                LOGGER.warning("Running in production mode over HTTP. "
                    + "Consider using HTTPS for secure communication.");
            }
        }

        for (var hook : startupHooks) {
            hook.run();
        }

        ServerAdapter adapter = resolveServerAdapter();
        adapter.start(this, host, port);

        if (shutdownHookThread != null) {
            Runtime.getRuntime().removeShutdownHook(shutdownHookThread);
        }
        shutdownHookThread = new Thread(() -> {
            for (var hook : shutdownHooks) {
                hook.run();
            }
        });
        Runtime.getRuntime().addShutdownHook(shutdownHookThread);
    }

    /**
     * Resolves the effective {@link ServerAdapter}, falling back to
     * {@link JavalinServerAdapter} when none was explicitly configured.
     *
     * @throws RuntimeException if no adapter is set and Javalin is not on the classpath
     */
    private ServerAdapter resolveServerAdapter() {
        if (serverAdapter != null) {
            return serverAdapter;
        }
        var javalin = JavalinServerAdapter.createIfAvailable(corsOrigins);
        if (javalin == null) {
            throw new RuntimeException(
                "Javalin not found. Add 'io.javalin:javalin' dependency or provide a custom ServerAdapter."
            );
        }
        return javalin;
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
        String url = resolveTargetUrl(target);
        return resolveNetwork().callRemoteSkill(url, skill, params, timeoutSeconds);
    }

    /**
     * Delegate a skill call to a remote agent, returning a {@link TaskHandle}
     * that carries the remote task ID for follow-up operations.
     */
    public TaskHandle delegateWithHandle(String target, String skill, Map<String, Object> params) throws Exception {
        return delegateWithHandle(target, skill, params, 30);
    }

    public TaskHandle delegateWithHandle(String target, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        String url = resolveTargetUrl(target);
        return resolveNetwork().callRemoteSkillWithHandle(url, skill, params, timeoutSeconds);
    }

    /**
     * Stream text chunks from a remote agent skill via SSE.
     *
     * <p>The target can be a full URL or a name registered in this agent's network.
     * The remote agent must support streaming.
     *
     * @param target         agent URL or registered name
     * @param skill          the skill to invoke
     * @param params         skill parameters
     * @param timeoutSeconds HTTP timeout
     * @return a StreamResult that yields String chunks as they arrive
     */
    public StreamingHandler.StreamResult streamDelegate(
            String target, String skill, Map<String, Object> params, int timeoutSeconds) {
        String url = resolveTargetUrl(target);
        return resolveNetwork().streamRemoteSkill(url, skill, params, timeoutSeconds);
    }

    /**
     * Stream text chunks from a remote agent skill via SSE with default timeout.
     */
    public StreamingHandler.StreamResult streamDelegate(
            String target, String skill, Map<String, Object> params) {
        return streamDelegate(target, skill, params, 30);
    }

    /**
     * Resolve a target string (name or URL) to a URL.
     */
    private String resolveTargetUrl(String target) {
        if (target.startsWith("http://") || target.startsWith("https://")) {
            return target;
        }
        if (network != null) {
            var resolved = network.get(target);
            if (resolved.isEmpty()) {
                throw new IllegalArgumentException(
                    "Agent '" + target + "' not found in network. Available: " + network.list().keySet()
                );
            }
            return resolved.get();
        }
        throw new IllegalArgumentException("No network configured and target is not a URL: " + target);
    }

    /**
     * Return the existing network or a fresh one for ad-hoc URL-based calls.
     */
    private AgentNetwork resolveNetwork() {
        return network != null ? network : new AgentNetwork();
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
    public TaskPushRegistry getPushRegistry() { return pushRegistry; }

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
        private ServerAdapter serverAdapter;

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

        public Builder serverAdapter(ServerAdapter adapter) {
            this.serverAdapter = adapter;
            return this;
        }

        public Agent build() {
            Objects.requireNonNull(name, "name is required");
            Objects.requireNonNull(description, "description is required");
            return new Agent(this);
        }
    }
}
