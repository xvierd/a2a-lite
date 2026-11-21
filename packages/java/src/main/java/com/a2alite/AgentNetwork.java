package com.a2alite;

import com.a2alite.errors.RemoteAgentException;
import com.a2alite.auth.CredentialProvider;
import com.a2alite.streaming.StreamingHandler;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;
import java.util.logging.Level;

/**
 * Registry of named remote A2A agents.
 *
 * Provides a simple way to manage and call multiple remote agents
 * by name instead of URL. Uses java.net.http.HttpClient (no new deps).
 *
 * Example:
 * <pre>{@code
 * var network = new AgentNetwork();
 * network.add("weather", "http://weather:8787");
 * var result = network.call("weather", "forecast", Map.of("city", "NYC"));
 * }</pre>
 */
public class AgentNetwork {
    private static final Logger LOGGER = Logger.getLogger(AgentNetwork.class.getName());
    private final Map<String, String> agents;
    // Index by discovery URL: two cards can advertise the same endpoint with different tenants.
    private final Map<String, List<AgentCardInfo>> cards;
    private final Map<String, CredentialProvider> requestHeaders;
    private final HttpClient httpClient;
    private final String tenant;

    public AgentNetwork() {
        agents = new ConcurrentHashMap<>();
        cards = new ConcurrentHashMap<>();
        requestHeaders = new ConcurrentHashMap<>();
        httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10))
            .followRedirects(HttpClient.Redirect.NEVER).build();
        tenant = null;
    }

    public AgentNetwork(Map<String, String> agents) {
        this();
        agents.forEach(this::add);
    }

    private AgentNetwork(AgentNetwork source, String tenant) {
        this.agents = source.agents;
        this.cards = source.cards;
        this.requestHeaders = source.requestHeaders;
        this.httpClient = source.httpClient;
        this.tenant = Objects.requireNonNull(tenant);
    }

    /** Scope calls to a tenant without changing other callers' requests. */
    public AgentNetwork withTenant(String tenant) { return new AgentNetwork(this, tenant); }

    /** Configure fixed authentication headers for this endpoint. */
    public AgentNetwork withHeaders(String agentUrl, Map<String, String> headers) {
        var snapshot = Map.copyOf(headers);
        return withCredentials(agentUrl, destination -> snapshot);
    }

    /** Resolve credentials on every request, allowing rotation without replacing task handles. */
    public AgentNetwork withCredentials(String agentUrl, CredentialProvider provider) {
        requestHeaders.put(endpointKey(agentUrl), Objects.requireNonNull(provider));
        return this;
    }

    private static URI httpUri(String endpoint) {
        var uri = URI.create(endpoint).normalize();
        if (uri.getHost() == null || uri.getRawUserInfo() != null || uri.getRawFragment() != null
                || !("http".equalsIgnoreCase(uri.getScheme()) || "https".equalsIgnoreCase(uri.getScheme()))) {
            throw new IllegalArgumentException("Agent endpoint must be HTTP(S), without credentials or fragment");
        }
        return uri;
    }

    private static String endpointKey(String endpoint) {
        var uri = httpUri(endpoint);
        return uri.getRawQuery() == null ? uri.toString().replaceAll("/$", "") : uri.toString();
    }

    private static boolean sameOrigin(URI a, URI b) {
        return a.getScheme().equalsIgnoreCase(b.getScheme()) && a.getHost().equalsIgnoreCase(b.getHost())
            && effectivePort(a) == effectivePort(b);
    }

    private static int effectivePort(URI uri) {
        if (uri.getPort() >= 0) return uri.getPort();
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    private HttpRequest.Builder requestBuilder(String destination, String credentialEndpoint) {
        var target = httpUri(destination);
        if (!sameOrigin(target, httpUri(credentialEndpoint))) {
            throw new IllegalArgumentException("Credentials cannot cross agent origins");
        }
        var builder = HttpRequest.newBuilder(target);
        var provider = requestHeaders.get(endpointKey(credentialEndpoint));
        if (provider != null) {
            Map.copyOf(provider.headers(target)).forEach((name, value) -> {
                if (Set.of("host", "content-length", "transfer-encoding", "connection").contains(name.toLowerCase(Locale.ROOT))) {
                    throw new IllegalArgumentException("Credential provider cannot override transport headers");
                }
                builder.header(name, value);
            });
        }
        return builder.setHeader("A2A-Version", "1.0");
    }

    record Endpoint(String url, String credentialScope, String tenant) {}

    Endpoint endpoint(String url) {
        var key = endpointKey(url);
        var choices = cards.get(key);
        if (choices == null) return new Endpoint(url, key, tenant);
        var selected = select(choices);
        return new Endpoint(selected.getUrl(), key, selected.getTenant());
    }

    private AgentCardInfo select(List<AgentCardInfo> choices) {
        if (tenant == null) return choices.get(0);
        for (var choice : choices) {
            if (tenant.equals(choice.getTenant())) return choice;
        }
        for (var choice : choices) {
            if (choice.getTenant() == null) return choice;
        }
        throw new IllegalArgumentException("No supported JSON-RPC interface for the requested tenant");
    }

    public void add(String name, String url) { agents.put(name, endpointKey(url)); }

    /** Register a discovery base, optionally fetching its card before first use. */
    public AgentNetwork add(String name, String url, boolean autoDiscover) {
        if (autoDiscover) {
            try {
                discoverAgent(url);
            } catch (IllegalArgumentException incompatible) {
                throw incompatible;
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Agent discovery interrupted", interrupted);
            } catch (Exception e) {
                LOGGER.log(Level.WARNING, "Auto-discovery failed for " + name + " at " + url, e);
            }
        }
        add(name, url);
        return this;
    }

    public Optional<String> get(String name) { return Optional.ofNullable(agents.get(name)); }
    public boolean remove(String name) { return agents.remove(name) != null; }
    public Map<String, String> list() { return Collections.unmodifiableMap(agents); }
    public int size() { return agents.size(); }

    private String namedUrl(String name) {
        return get(name).orElseThrow(() -> new IllegalArgumentException(
            "Agent '" + name + "' not found in network. Available: " + agents.keySet()));
    }

    private Endpoint target(String nameOrUrl) {
        return endpoint(agents.getOrDefault(nameOrUrl, nameOrUrl));
    }

    public Object call(String name, String skill, Map<String, Object> params) throws Exception {
        return call(name, skill, params, 30);
    }

    public Object call(String name, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        return callRemoteSkill(namedUrl(name), skill, params, timeoutSeconds);
    }

    /**
     * Same as {@link #call(String, String, Map, int)} but returns a
     * {@link TaskHandle} containing the remote task ID.
     */
    public TaskHandle callWithHandle(String name, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        return callRemoteSkillWithHandle(namedUrl(name), skill, params, timeoutSeconds);
    }

    public Map<String, Object> broadcast(String skill, Map<String, Object> params) {
        return broadcast(skill, params, 30);
    }

    public Map<String, Object> broadcast(String skill, Map<String, Object> params, int timeoutSeconds) {
        var results = new HashMap<String, Object>();
        agents.forEach((name, url) -> {
            try {
                results.put(name, callRemoteSkill(url, skill, params, timeoutSeconds));
            } catch (Exception e) {
                results.put(name, Map.of("error", String.valueOf(e.getMessage()), "type", e.getClass().getSimpleName()));
            }
        });
        return results;
    }

    private Map<String, Object> skillParams(String skill, Map<String, Object> params) {
        var text = ClientRpc.encode(Map.of("skill", skill, "params", params));
        return Map.of("message", Map.of("role", "ROLE_USER", "messageId", ClientRpc.id(),
            "parts", List.of(Map.of("text", text))));
    }

    private HttpRequest request(Endpoint endpoint, String id, String method, Map<String, Object> params,
                                int timeoutSeconds, String accept) {
        var scoped = new HashMap<>(params);
        if (endpoint.tenant() != null) scoped.put("tenant", endpoint.tenant());
        var body = ClientRpc.encode(Map.of("jsonrpc", "2.0", "id", id, "method", method, "params", scoped));
        return requestBuilder(endpoint.url(), endpoint.credentialScope()).setHeader("Content-Type", "application/json")
            .setHeader("Accept", accept).timeout(Duration.ofSeconds(timeoutSeconds))
            .POST(HttpRequest.BodyPublishers.ofString(body)).build();
    }

    private Object rpc(Endpoint endpoint, String method, Map<String, Object> params, int timeoutSeconds) throws Exception {
        var id = ClientRpc.id();
        var req = request(endpoint, id, method, params, timeoutSeconds, "application/json");
        var response = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
        return ClientRpc.result(response.body(), id, response.statusCode());
    }

    public Object callRemoteSkill(String agentUrl, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        return extractResult(rpc(endpoint(agentUrl), "SendMessage", skillParams(skill, params), timeoutSeconds)).result();
    }

    /**
     * Same as {@link #callRemoteSkill} but returns a {@link TaskHandle}
     * carrying the remote task ID alongside the extracted result.
     */
    public TaskHandle callRemoteSkillWithHandle(String agentUrl, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        var route = endpoint(agentUrl);
        var result = extractResult(rpc(route, "SendMessage", skillParams(skill, params), timeoutSeconds));
        if (result.taskId() == null || result.taskId().isBlank()) {
            throw new RemoteAgentException("Remote agent returned only a Message; no task handle is available");
        }
        return new TaskHandle(result.taskId(), result.result(), route, this);
    }

    /**
     * Fetch the current state of a remote task by ID.
     *
     * <p>Sends a {@code GetTask} JSON-RPC request to the given agent URL.
     */
    public Object getRemoteTask(String agentUrl, String taskId, int timeoutSeconds) throws Exception {
        return getTaskResult(endpoint(agentUrl), taskId, timeoutSeconds);
    }

    Object getTaskResult(Endpoint route, String taskId, int timeoutSeconds) throws Exception {
        return extractResult(taskSnapshot(route, taskId, timeoutSeconds)).result();
    }

    /** Fetch the full protocol Task, including identity, status, history and artifacts. */
    public Map<String, Object> getRemoteTaskSnapshot(String agentUrl, String taskId, int timeoutSeconds) throws Exception {
        return taskSnapshot(endpoint(agentUrl), taskId, timeoutSeconds);
    }

    Map<String, Object> taskSnapshot(Endpoint route, String taskId, int timeoutSeconds) throws Exception {
        return checkedTask(rpc(route, "GetTask", Map.of("id", taskId), timeoutSeconds), taskId);
    }

    private Map<String, Object> checkedTask(Object result, String taskId) {
        var task = ClientRpc.object(result, "Task");
        if (!taskId.equals(task.get("id"))) throw new RemoteAgentException("Peer did not return the requested Task");
        return task;
    }

    /**
     * Cancel a remote task by ID.
     *
     * <p>Sends a {@code CancelTask} JSON-RPC request to the given agent URL.
     */
    public Object cancelRemoteTask(String agentUrl, String taskId, int timeoutSeconds) throws Exception {
        return cancel(endpoint(agentUrl), taskId, timeoutSeconds);
    }

    Object cancel(Endpoint route, String taskId, int timeoutSeconds) throws Exception {
        var result = rpc(route, "CancelTask", Map.of("id", taskId), timeoutSeconds);
        return extractResult(checkedTask(result, taskId)).result();
    }

    /**
     * Fetch the current status of a task running on a named agent.
     *
     * @param name           the registered agent name
     * @param taskId         the remote task ID
     * @param timeoutSeconds HTTP timeout
     * @return the task status from the remote agent
     */
    public Object getTask(String name, String taskId, int timeoutSeconds) throws Exception {
        return getRemoteTask(namedUrl(name), taskId, timeoutSeconds);
    }

    /**
     * Fetch the current status of a task running on a named agent using the default 10-second timeout.
     */
    public Object getTask(String name, String taskId) throws Exception { return getTask(name, taskId, 10); }

    /**
     * Request cancellation of a task running on a named agent.
     *
     * @param name           the registered agent name
     * @param taskId         the remote task ID
     * @param timeoutSeconds HTTP timeout
     * @return the cancellation result from the remote agent
     */
    public Object cancelTask(String name, String taskId, int timeoutSeconds) throws Exception {
        return cancelRemoteTask(namedUrl(name), taskId, timeoutSeconds);
    }

    /**
     * Request cancellation of a task running on a named agent using the default 10-second timeout.
     */
    public Object cancelTask(String name, String taskId) throws Exception { return cancelTask(name, taskId, 10); }

    /** One ListTasks page. Pass nextPageToken to the next request until it is empty. */
    public record TaskPage(List<Map<String, Object>> tasks, String nextPageToken) {}

    public TaskPage listTasks(String nameOrUrl, int pageSize, String pageToken, int timeoutSeconds) throws Exception {
        var params = new HashMap<String, Object>();
        params.put("pageSize", pageSize);
        if (pageToken != null && !pageToken.isEmpty()) params.put("pageToken", pageToken);
        var page = ClientRpc.object(rpc(target(nameOrUrl), "ListTasks", params, timeoutSeconds), "ListTasks result");
        // Some protobuf-based peers omit the default empty cursor on the final page.
        if (!(page.get("tasks") instanceof List<?> entries) || !(page.getOrDefault("nextPageToken", "") instanceof String token)) {
            throw new RemoteAgentException("Invalid ListTasks page", page);
        }
        return new TaskPage(entries.stream().map(entry -> ClientRpc.object(entry, "Task")).toList(), token);
    }

    public TaskPage listTasks(String nameOrUrl, int pageSize, String pageToken) throws Exception {
        return listTasks(nameOrUrl, pageSize, pageToken, 10);
    }

    /**
     * Discover a remote agent by fetching its card from
     * {@code agentUrl/.well-known/agent-card.json}.
     */
    public AgentCardInfo discoverAgent(String agentUrl) throws Exception { return discoverAgent(agentUrl, 10); }

    /**
     * Discover a remote agent with a custom timeout.
     */
    public AgentCardInfo discoverAgent(String agentUrl, int timeoutSeconds) throws Exception {
        var base = endpointKey(agentUrl);
        var uri = httpUri(base);
        var cardPath = uri.getRawPath().replaceAll("/$", "") + "/.well-known/agent-card.json";
        var cardUri = uri.resolve(cardPath);
        var req = requestBuilder(cardUri.toString(), base).setHeader("Accept", "application/json")
            .GET().timeout(Duration.ofSeconds(timeoutSeconds)).build();
        var response = httpClient.send(req, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RemoteAgentException("Agent card discovery returned HTTP " + response.statusCode());
        }
        var choices = parseInterfaces(ClientRpc.decode(response.body()), uri);
        var card = select(choices);
        cards.put(base, choices);
        return card;
    }

    public AgentCardInfo discoverNamed(String name) throws Exception { return discoverAgent(namedUrl(name)); }

    /**
     * Return the cached card for a named agent, if available.
     */
    public Optional<AgentCardInfo> getCard(String name) { return get(name).map(cards::get).map(this::select); }

    private TaskEventStream events(Endpoint route, String method, Map<String, Object> params, int timeoutSeconds, String taskId) {
        var id = ClientRpc.id();
        var req = request(route, id, method, params, timeoutSeconds, "text/event-stream, application/json");
        return new TaskEventStream(httpClient.sendAsync(req, HttpResponse.BodyHandlers.ofInputStream()), id, taskId);
    }

    /** Stream complete events, including all message parts, artifacts and metadata. */
    public TaskEventStream streamEvents(String nameOrUrl, String skill, Map<String, Object> params, int timeoutSeconds) {
        return events(target(nameOrUrl), "SendStreamingMessage", skillParams(skill, params), timeoutSeconds, null);
    }

    public TaskEventStream streamEvents(String nameOrUrl, String skill, Map<String, Object> params) {
        return streamEvents(nameOrUrl, skill, params, 30);
    }

    /** Subscribe to updates for an existing task. Each call opens a fresh SSE subscription. */
    public TaskEventStream subscribeTask(String nameOrUrl, String taskId, int timeoutSeconds) {
        return subscribeTask(target(nameOrUrl), taskId, timeoutSeconds);
    }

    public TaskEventStream subscribeTask(String nameOrUrl, String taskId) { return subscribeTask(nameOrUrl, taskId, 30); }

    TaskEventStream subscribeTask(Endpoint route, String taskId, int timeoutSeconds) {
        return events(route, "SubscribeToTask", Map.of("id", taskId), timeoutSeconds, taskId);
    }

    public StreamingHandler.StreamResult streamRemoteSkill(String agentUrl, String skill, Map<String, Object> params, int timeoutSeconds) {
        return events(endpoint(agentUrl), "SendStreamingMessage", skillParams(skill, params), timeoutSeconds, null).textChunks();
    }

    public StreamingHandler.StreamResult streamRemoteSkill(String agentUrl, String skill, Map<String, Object> params) {
        return streamRemoteSkill(agentUrl, skill, params, 30);
    }

    public StreamingHandler.StreamResult stream(String name, String skill, Map<String, Object> params, int timeoutSeconds) {
        return streamRemoteSkill(namedUrl(name), skill, params, timeoutSeconds);
    }

    public StreamingHandler.StreamResult stream(String name, String skill, Map<String, Object> params) {
        return stream(name, skill, params, 30);
    }

    /**
     * Register a per-task push notification webhook on a remote agent.
     *
     * @param agentUrl       the agent's base URL
     * @param taskId         the task ID to subscribe to
     * @param webhookUrl     the webhook URL to receive notifications
     * @param token          optional bearer token, or {@code null}
     * @param timeoutSeconds HTTP timeout
     * @return the JSON-RPC result
     */
    public Object setTaskPushNotification(String agentUrl, String taskId, String webhookUrl, String token, int timeoutSeconds) throws Exception {
        return setPush(endpoint(agentUrl), taskId, webhookUrl, token, timeoutSeconds);
    }

    Object setPush(Endpoint route, String taskId, String webhookUrl, String token, int timeoutSeconds) throws Exception {
        var params = new HashMap<String, Object>();
        params.put("taskId", taskId);
        params.put("url", webhookUrl);
        if (token != null) params.put("token", token);
        return rpc(route, "CreateTaskPushNotificationConfig", params, timeoutSeconds);
    }

    /**
     * Register a per-task push notification webhook without a bearer token.
     */
    public Object setTaskPushNotification(String agentUrl, String taskId, String webhookUrl) throws Exception {
        return setTaskPushNotification(agentUrl, taskId, webhookUrl, null, 10);
    }

    /**
     * Retrieve the push notification config for a task on a remote agent.
     *
     * @param agentUrl       the agent's base URL
     * @param taskId         the task ID
     * @param timeoutSeconds HTTP timeout
     * @return the JSON-RPC result containing the push config
     */
    public Object getTaskPushNotification(String agentUrl, String taskId, int timeoutSeconds) throws Exception {
        return getPush(endpoint(agentUrl), taskId, timeoutSeconds);
    }

    Object getPush(Endpoint route, String taskId, int timeoutSeconds) throws Exception {
        return rpc(route, "GetTaskPushNotificationConfig", Map.of("taskId", taskId, "id", taskId), timeoutSeconds);
    }

    /**
     * Retrieve the push notification config for a task with default timeout.
     */
    public Object getTaskPushNotification(String agentUrl, String taskId) throws Exception {
        return getTaskPushNotification(agentUrl, taskId, 10);
    }

    /**
     * Delete the push notification config for a task on a remote agent.
     *
     * @param agentUrl       the agent's base URL
     * @param taskId         the task ID
     * @param timeoutSeconds HTTP timeout
     * @return the JSON-RPC result
     */
    public Object deleteTaskPushNotification(String agentUrl, String taskId, int timeoutSeconds) throws Exception {
        return deletePush(endpoint(agentUrl), taskId, timeoutSeconds);
    }

    Object deletePush(Endpoint route, String taskId, int timeoutSeconds) throws Exception {
        return rpc(route, "DeleteTaskPushNotificationConfig", Map.of("taskId", taskId, "id", taskId), timeoutSeconds);
    }

    /**
     * Delete the push notification config for a task with default timeout.
     */
    public Object deleteTaskPushNotification(String agentUrl, String taskId) throws Exception {
        return deleteTaskPushNotification(agentUrl, taskId, 10);
    }

    private record InternalResult(String taskId, Object result) {}

    @SuppressWarnings("unchecked")
    private InternalResult extractResult(Object value) {
        // A2A v1.0: result is { message: {...} } or { task: {...} }
        var envelope = ClientRpc.object(value, "A2A result");
        var result = envelope.get("message") instanceof Map<?, ?> m ? (Map<String, Object>) m
            : envelope.get("task") instanceof Map<?, ?> t ? (Map<String, Object>) t
            : envelope;

        // Task ID from the v1.0 response envelope:
        // result.task.id or result.id with status (bare Task)
        String taskId = null;
        if (envelope.get("task") instanceof Map<?, ?> taskObj && ((Map<String, Object>) taskObj).get("id") != null) {
            taskId = String.valueOf(((Map<String, Object>) taskObj).get("id"));
        } else if (envelope.get("id") != null && envelope.get("status") instanceof Map<?, ?>) {
            taskId = String.valueOf(envelope.get("id"));
        }

        // Text parts on the message/task itself
        var text = firstText(result);
        if (text != null) {
            return new InternalResult(taskId, parseJsonOrText(text));
        }

        // Task results: status message, then artifact parts
        if (result.get("status") instanceof Map<?, ?> status && ((Map<String, Object>) status).get("message") instanceof Map<?, ?> sm) {
            text = firstText((Map<String, Object>) sm);
            if (text != null) {
                return new InternalResult(taskId, parseJsonOrText(text));
            }
        }

        if (result.get("artifacts") instanceof List<?> artifacts) {
            for (var artifact : artifacts) {
                if (artifact instanceof Map<?, ?> artifactMap) {
                    text = firstText((Map<String, Object>) artifactMap);
                    if (text != null) {
                        return new InternalResult(taskId, parseJsonOrText(text));
                    }
                }
            }
        }

        return new InternalResult(taskId, result);
    }

    /**
     * Returns the text of the first text part in a message/artifact-like map,
     * or {@code null} if there is none (A2A v1.0: text parts are {@code {"text": ...}}).
     */
    @SuppressWarnings("unchecked")
    private static String firstText(Map<String, Object> container) {
        if (container.get("parts") instanceof List<?> parts) {
            for (var part : parts) {
                if (part instanceof Map<?, ?> partMap && ((Map<String, Object>) partMap).get("text") instanceof String text) {
                    return text;
                }
            }
        }
        return null;
    }

    private Object parseJsonOrText(String text) {
        try {
            return ClientRpc.JSON.readValue(text, Object.class);
        } catch (Exception e) {
            return text;
        }
    }

    AgentCardInfo parseAgentCard(Map<String, Object> raw) { return select(parseInterfaces(raw, null)); }

    @SuppressWarnings("unchecked")
    private List<AgentCardInfo> parseInterfaces(Map<String, Object> raw, URI origin) {
        if (!raw.containsKey("supportedInterfaces")
                && (raw.containsKey("url") || raw.containsKey("protocolVersion"))) {
            throw new IllegalArgumentException("Remote agent speaks A2A 0.3, not supported by a2a-lite 1.0");
        }

        var name = (String) raw.getOrDefault("name", "");
        var description = (String) raw.getOrDefault("description", "");
        var version = (String) raw.getOrDefault("version", "");
        var skills = new ArrayList<Map<String, Object>>();
        if (raw.get("skills") instanceof List<?> items) {
            for (var item : items) {
                if (item instanceof Map<?, ?> skill) skills.add((Map<String, Object>) skill);
            }
        }
        var capabilities = raw.get("capabilities") instanceof Map<?, ?> caps ? caps : Map.of();
        var choices = new ArrayList<AgentCardInfo>();
        if (raw.get("supportedInterfaces") instanceof List<?> interfaces) {
            for (var item : interfaces) {
                if (!(item instanceof Map<?, ?> iface) || !"JSONRPC".equals(iface.get("protocolBinding"))
                        || !(iface.get("protocolVersion") instanceof String protocol) || !protocol.matches("1\\.0(?:\\.[0-9]+)?")
                        || !(iface.get("url") instanceof String url)
                        || (iface.containsKey("tenant") && !(iface.get("tenant") instanceof String))) continue;
                try {
                    var uri = httpUri(url);
                    if (origin != null && !sameOrigin(uri, origin)) continue;
                } catch (IllegalArgumentException invalidUrl) {
                    continue;
                }
                choices.add(new AgentCardInfo(name, description, url, (String) iface.get("tenant"), version, skills,
                    Boolean.TRUE.equals(capabilities.get("streaming")), Boolean.TRUE.equals(capabilities.get("pushNotifications")), raw));
            }
        }
        if (choices.isEmpty()) throw new IllegalArgumentException("No supported same-origin A2A 1.0 JSON-RPC interface");
        return List.copyOf(choices);
    }
}
