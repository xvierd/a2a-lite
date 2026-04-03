package com.a2alite;

import com.a2alite.errors.RemoteAgentException;
import com.a2alite.streaming.StreamingHandler;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.atomic.AtomicReference;
import java.util.logging.Logger;
import java.util.logging.Level;
import java.util.stream.Stream;

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
    private final Map<String, String> agents = new ConcurrentHashMap<>();
    private final Map<String, AgentCardInfo> cards = new ConcurrentHashMap<>();
    private final HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();
    private final ObjectMapper mapper = new ObjectMapper();

    public AgentNetwork() {}

    public AgentNetwork(Map<String, String> agents) {
        for (var entry : agents.entrySet()) {
            this.agents.put(entry.getKey(), entry.getValue().replaceAll("/$", ""));
        }
    }

    public void add(String name, String url) {
        agents.put(name, url.replaceAll("/$", ""));
    }

    /**
     * Register a named agent with optional auto-discovery.
     *
     * <p>When {@code autoDiscover} is {@code true}, the agent's card is
     * fetched from {@code url/.well-known/agent.json} and cached.
     */
    public AgentNetwork add(String name, String url, boolean autoDiscover) {
        agents.put(name, url.replaceAll("/$", ""));
        if (autoDiscover) {
            try {
                var card = discoverAgent(url);
                cards.put(name, card);
            } catch (Exception e) {
                LOGGER.log(Level.WARNING, "Auto-discovery failed for " + name + " at " + url, e);
            }
        }
        return this;
    }

    public Optional<String> get(String name) {
        return Optional.ofNullable(agents.get(name));
    }

    public boolean remove(String name) {
        return agents.remove(name) != null;
    }

    public Map<String, String> list() {
        return Collections.unmodifiableMap(agents);
    }

    public Object call(String name, String skill, Map<String, Object> params) throws Exception {
        return call(name, skill, params, 30);
    }

    public Object call(String name, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        var url = agents.get(name);
        if (url == null) {
            throw new IllegalArgumentException(
                "Agent '" + name + "' not found in network. Available: " + agents.keySet()
            );
        }
        return callRemoteSkill(url, skill, params, timeoutSeconds);
    }

    /**
     * Same as {@link #call(String, String, Map, int)} but returns a
     * {@link TaskHandle} containing the remote task ID.
     */
    public TaskHandle callWithHandle(String name, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        var url = agents.get(name);
        if (url == null) {
            throw new IllegalArgumentException(
                "Agent '" + name + "' not found in network. Available: " + agents.keySet()
            );
        }
        return callRemoteSkillWithHandle(url, skill, params, timeoutSeconds);
    }

    public Map<String, Object> broadcast(String skill, Map<String, Object> params) {
        return broadcast(skill, params, 30);
    }

    public Map<String, Object> broadcast(String skill, Map<String, Object> params, int timeoutSeconds) {
        var results = new HashMap<String, Object>();
        for (var entry : agents.entrySet()) {
            try {
                results.put(entry.getKey(), callRemoteSkill(entry.getValue(), skill, params, timeoutSeconds));
            } catch (Exception e) {
                results.put(entry.getKey(), Map.of("error", e.getMessage(), "type", e.getClass().getSimpleName()));
            }
        }
        return results;
    }

    public Object callRemoteSkill(String agentUrl, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        var internalResult = callRemoteSkillInternal(agentUrl, skill, params, timeoutSeconds);
        return internalResult.result;
    }

    /**
     * Same as {@link #callRemoteSkill} but returns a {@link TaskHandle}
     * carrying the remote task ID alongside the extracted result.
     */
    public TaskHandle callRemoteSkillWithHandle(String agentUrl, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        var internalResult = callRemoteSkillInternal(agentUrl, skill, params, timeoutSeconds);
        return new TaskHandle(internalResult.taskId, internalResult.result, agentUrl, this);
    }

    /**
     * Fetch the current state of a remote task by ID.
     *
     * <p>Sends a {@code tasks/get} JSON-RPC request to the given agent URL.
     */
    public Object getRemoteTask(String agentUrl, String taskId, int timeoutSeconds) throws Exception {
        var requestBody = mapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0",
            "method", "tasks/get",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of("id", taskId)
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody))
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .build();

        var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RemoteAgentException("Remote agent returned HTTP " + response.statusCode());
        }

        @SuppressWarnings("unchecked")
        var data = mapper.readValue(response.body(), Map.class);
        return extractResult(data).result;
    }

    /**
     * Cancel a remote task by ID.
     *
     * <p>Sends a {@code tasks/cancel} JSON-RPC request to the given agent URL.
     */
    public Object cancelRemoteTask(String agentUrl, String taskId, int timeoutSeconds) throws Exception {
        var requestBody = mapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0",
            "method", "tasks/cancel",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of("id", taskId)
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody))
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .build();

        var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RemoteAgentException("Remote agent returned HTTP " + response.statusCode());
        }

        @SuppressWarnings("unchecked")
        var data = mapper.readValue(response.body(), Map.class);
        return extractResult(data).result;
    }

    // ---- Name-based task operations -------------------------------------------

    /**
     * Fetch the current status of a task running on a named agent.
     *
     * @param name           the registered agent name
     * @param taskId         the remote task ID
     * @param timeoutSeconds HTTP timeout
     * @return the task status from the remote agent
     */
    public Object getTask(String name, String taskId, int timeoutSeconds) throws Exception {
        var url = agents.get(name);
        if (url == null) {
            throw new IllegalArgumentException(
                "Agent '" + name + "' not found in network. Available: " + agents.keySet()
            );
        }
        return getRemoteTask(url, taskId, timeoutSeconds);
    }

    /**
     * Fetch the current status of a task running on a named agent using the default 10-second timeout.
     */
    public Object getTask(String name, String taskId) throws Exception {
        return getTask(name, taskId, 10);
    }

    /**
     * Request cancellation of a task running on a named agent.
     *
     * @param name           the registered agent name
     * @param taskId         the remote task ID
     * @param timeoutSeconds HTTP timeout
     * @return the cancellation result from the remote agent
     */
    public Object cancelTask(String name, String taskId, int timeoutSeconds) throws Exception {
        var url = agents.get(name);
        if (url == null) {
            throw new IllegalArgumentException(
                "Agent '" + name + "' not found in network. Available: " + agents.keySet()
            );
        }
        return cancelRemoteTask(url, taskId, timeoutSeconds);
    }

    /**
     * Request cancellation of a task running on a named agent using the default 10-second timeout.
     */
    public Object cancelTask(String name, String taskId) throws Exception {
        return cancelTask(name, taskId, 10);
    }

    // ---- Agent Card Discovery ------------------------------------------------

    /**
     * Discover a remote agent by fetching its card from
     * {@code agentUrl/.well-known/agent.json}.
     */
    public AgentCardInfo discoverAgent(String agentUrl) throws Exception {
        return discoverAgent(agentUrl, 10);
    }

    /**
     * Discover a remote agent with a custom timeout.
     */
    @SuppressWarnings("unchecked")
    public AgentCardInfo discoverAgent(String agentUrl, int timeoutSeconds) throws Exception {
        var cleanUrl = agentUrl.replaceAll("/$", "");
        var request = HttpRequest.newBuilder()
            .uri(URI.create(cleanUrl + "/.well-known/agent.json"))
            .header("Accept", "application/json")
            .GET()
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .build();

        var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RemoteAgentException("Agent card discovery returned HTTP " + response.statusCode());
        }

        var raw = (Map<String, Object>) mapper.readValue(response.body(), Map.class);
        return parseAgentCard(raw);
    }

    /**
     * Fetch and cache the agent card for a named, registered agent.
     *
     * @param name the registered agent name
     * @return the discovered agent card
     * @throws IllegalArgumentException if the name is not registered
     */
    public AgentCardInfo discoverNamed(String name) throws Exception {
        var url = agents.get(name);
        if (url == null) {
            throw new IllegalArgumentException(
                "Agent '" + name + "' not found in network. Available: " + agents.keySet()
            );
        }
        var card = discoverAgent(url);
        cards.put(name, card);
        return card;
    }

    /**
     * Return the cached card for a named agent, if available.
     */
    public Optional<AgentCardInfo> getCard(String name) {
        return Optional.ofNullable(cards.get(name));
    }

    // ---- Streaming -----------------------------------------------------------

    /**
     * Stream text chunks from a remote A2A agent skill via SSE.
     * The remote agent must support streaming.
     *
     * @param agentUrl       the agent's base URL
     * @param skill          the skill to invoke
     * @param params         skill parameters
     * @param timeoutSeconds HTTP timeout
     * @return a StreamResult that yields String chunks as they arrive
     */
    public StreamingHandler.StreamResult streamRemoteSkill(
            String agentUrl, String skill, Map<String, Object> params, int timeoutSeconds) {
        // Use a queue + background thread so errors propagate to the consuming iterator
        var queue = new LinkedBlockingQueue<Object>();
        var error = new AtomicReference<Exception>();
        var SENTINEL = new Object();

        new Thread(() -> {
            try {
                var message = mapper.writeValueAsString(Map.of("skill", skill, "params", params));
                var requestBody = mapper.writeValueAsString(Map.of(
                    "jsonrpc", "2.0",
                    "method", "message/stream",
                    "id", UUID.randomUUID().toString().replace("-", ""),
                    "params", Map.of(
                        "message", Map.of(
                            "role", "user",
                            "parts", List.of(Map.of("type", "text", "text", message)),
                            "messageId", UUID.randomUUID().toString().replace("-", "")
                        )
                    )
                ));

                var request = HttpRequest.newBuilder()
                    .uri(URI.create(agentUrl))
                    .header("Content-Type", "application/json")
                    .header("Accept", "text/event-stream")
                    .POST(HttpRequest.BodyPublishers.ofString(requestBody))
                    .timeout(Duration.ofSeconds(timeoutSeconds))
                    .build();

                HttpResponse<Stream<String>> response = httpClient.send(
                    request, HttpResponse.BodyHandlers.ofLines());

                if (response.statusCode() < 200 || response.statusCode() >= 300) {
                    throw new RemoteAgentException(
                        "Remote agent returned HTTP " + response.statusCode());
                }

                try (var lines = response.body()) {
                    var iter = lines.iterator();
                    while (iter.hasNext()) {
                        var line = iter.next();
                        if (!line.startsWith("data:")) continue;
                        var json = line.substring(5).trim();
                        if (json.isEmpty()) continue;

                        @SuppressWarnings("unchecked")
                        var event = (Map<String, Object>) mapper.readValue(json, Map.class);

                        // Check for failed status
                        @SuppressWarnings("unchecked")
                        var status = (Map<String, Object>) event.get("status");
                        if (status != null) {
                            var state = (String) status.get("state");
                            if ("failed".equals(state)) {
                                throw new RemoteAgentException(
                                    "Remote agent task failed", event);
                            }
                        }

                        // Extract artifact text chunks
                        @SuppressWarnings("unchecked")
                        var artifact = (Map<String, Object>) event.get("artifact");
                        if (artifact != null) {
                            @SuppressWarnings("unchecked")
                            var parts = (List<Map<String, Object>>) artifact.get("parts");
                            if (parts != null) {
                                for (var part : parts) {
                                    if ("text".equals(part.get("kind")) || "text".equals(part.get("type"))) {
                                        queue.put(part.get("text"));
                                    }
                                }
                            }
                        }

                        // Stop on final event
                        if (Boolean.TRUE.equals(event.get("final"))) {
                            break;
                        }
                    }
                }
            } catch (Exception e) {
                error.set(e);
            } finally {
                try { queue.put(SENTINEL); } catch (InterruptedException ignored) {
                    Thread.currentThread().interrupt();
                }
            }
        }).start();

        return new StreamingHandler.StreamResult() {
            @Override
            public Iterator<Object> iterator() {
                return new Iterator<>() {
                    private Object next = null;

                    @Override
                    public boolean hasNext() {
                        if (next != null) return true;
                        try {
                            next = queue.take();
                            if (next == SENTINEL) {
                                next = null;
                                // Check for error after sentinel
                                var ex = error.get();
                                if (ex != null) {
                                    throw new RuntimeException(ex);
                                }
                                return false;
                            }
                            return true;
                        } catch (InterruptedException e) {
                            Thread.currentThread().interrupt();
                            return false;
                        }
                    }

                    @Override
                    public Object next() {
                        if (next == null && !hasNext()) {
                            throw new java.util.NoSuchElementException();
                        }
                        Object result = next;
                        next = null;
                        return result;
                    }
                };
            }
        };
    }

    /**
     * Stream text chunks from a remote A2A agent skill via SSE with default timeout.
     */
    public StreamingHandler.StreamResult streamRemoteSkill(
            String agentUrl, String skill, Map<String, Object> params) {
        return streamRemoteSkill(agentUrl, skill, params, 30);
    }

    /**
     * Stream text chunks from a named remote agent via SSE.
     *
     * @param name           the registered agent name
     * @param skill          the skill to invoke
     * @param params         skill parameters
     * @param timeoutSeconds HTTP timeout
     * @return a StreamResult that yields String chunks as they arrive
     */
    public StreamingHandler.StreamResult stream(
            String name, String skill, Map<String, Object> params, int timeoutSeconds) {
        var url = agents.get(name);
        if (url == null) {
            throw new IllegalArgumentException(
                "Agent '" + name + "' not found in network. Available: " + agents.keySet()
            );
        }
        return streamRemoteSkill(url, skill, params, timeoutSeconds);
    }

    /**
     * Stream text chunks from a named remote agent via SSE with default timeout.
     */
    public StreamingHandler.StreamResult stream(
            String name, String skill, Map<String, Object> params) {
        return stream(name, skill, params, 30);
    }

    // ---- Per-task push notification methods -----------------------------------

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
        var pushConfig = new HashMap<String, Object>();
        pushConfig.put("url", webhookUrl);
        if (token != null) {
            pushConfig.put("token", token);
        }

        var requestBody = mapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0",
            "method", "tasks/pushNotification/set",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of(
                "id", taskId,
                "pushNotificationConfig", pushConfig
            )
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody))
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .build();

        var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RemoteAgentException("Remote agent returned HTTP " + response.statusCode());
        }

        @SuppressWarnings("unchecked")
        var data = mapper.readValue(response.body(), Map.class);
        if (data.containsKey("error")) {
            throw new RemoteAgentException(mapper.writeValueAsString(data.get("error")), data);
        }
        return data.get("result");
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
        var requestBody = mapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0",
            "method", "tasks/pushNotification/get",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of("id", taskId)
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody))
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .build();

        var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RemoteAgentException("Remote agent returned HTTP " + response.statusCode());
        }

        @SuppressWarnings("unchecked")
        var data = mapper.readValue(response.body(), Map.class);
        if (data.containsKey("error")) {
            throw new RemoteAgentException(mapper.writeValueAsString(data.get("error")), data);
        }
        return data.get("result");
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
        var requestBody = mapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0",
            "method", "tasks/pushNotification/delete",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of("id", taskId)
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody))
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .build();

        var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RemoteAgentException("Remote agent returned HTTP " + response.statusCode());
        }

        @SuppressWarnings("unchecked")
        var data = mapper.readValue(response.body(), Map.class);
        if (data.containsKey("error")) {
            throw new RemoteAgentException(mapper.writeValueAsString(data.get("error")), data);
        }
        return data.get("result");
    }

    /**
     * Delete the push notification config for a task with default timeout.
     */
    public Object deleteTaskPushNotification(String agentUrl, String taskId) throws Exception {
        return deleteTaskPushNotification(agentUrl, taskId, 10);
    }

    // ---- Internal helpers ----------------------------------------------------

    /**
     * Internal result type that carries both the extracted result and the
     * task ID from the JSON-RPC response.
     */
    static class InternalResult {
        final String taskId;
        final Object result;

        InternalResult(String taskId, Object result) {
            this.taskId = taskId;
            this.result = result;
        }
    }

    private InternalResult callRemoteSkillInternal(String agentUrl, String skill, Map<String, Object> params, int timeoutSeconds) throws Exception {
        var message = mapper.writeValueAsString(Map.of("skill", skill, "params", params));
        var requestBody = mapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0",
            "method", "message/send",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of(
                "message", Map.of(
                    "role", "user",
                    "parts", List.of(Map.of("type", "text", "text", message)),
                    "messageId", UUID.randomUUID().toString().replace("-", "")
                )
            )
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .POST(HttpRequest.BodyPublishers.ofString(requestBody))
            .timeout(Duration.ofSeconds(timeoutSeconds))
            .build();

        var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new RemoteAgentException("Remote agent returned HTTP " + response.statusCode());
        }

        @SuppressWarnings("unchecked")
        var data = mapper.readValue(response.body(), Map.class);
        return extractResult(data);
    }

    @SuppressWarnings("unchecked")
    private InternalResult extractResult(Map<String, Object> response) throws Exception {
        if (response.containsKey("error")) {
            var error = response.get("error");
            var message = error instanceof String ? (String) error : mapper.writeValueAsString(error);
            throw new RemoteAgentException(message, response);
        }

        var result = (Map<String, Object>) response.getOrDefault("result", Map.of());
        var taskId = result.containsKey("id") ? String.valueOf(result.get("id")) : null;

        // A2A responses may nest parts inside artifacts or at the top-level result
        var parts = (List<Map<String, Object>>) result.getOrDefault("parts", List.of());

        for (var part : parts) {
            if ("text".equals(part.get("kind")) || "text".equals(part.get("type"))) {
                var text = (String) part.get("text");
                try {
                    return new InternalResult(taskId, mapper.readValue(text, Object.class));
                } catch (Exception e) {
                    return new InternalResult(taskId, text);
                }
            }
        }

        return new InternalResult(taskId, result);
    }

    @SuppressWarnings("unchecked")
    AgentCardInfo parseAgentCard(Map<String, Object> raw) {
        var name = (String) raw.getOrDefault("name", "");
        var description = (String) raw.getOrDefault("description", "");
        var url = (String) raw.getOrDefault("url", "");
        var version = (String) raw.getOrDefault("version", "");

        var skillsList = new ArrayList<Map<String, Object>>();
        var skillsRaw = raw.get("skills");
        if (skillsRaw instanceof List) {
            for (var s : (List<?>) skillsRaw) {
                if (s instanceof Map) {
                    skillsList.add((Map<String, Object>) s);
                }
            }
        }

        boolean streaming = false;
        boolean push = false;
        var capabilities = raw.get("capabilities");
        if (capabilities instanceof Map) {
            var caps = (Map<String, Object>) capabilities;
            streaming = Boolean.TRUE.equals(caps.get("streaming"));
            push = Boolean.TRUE.equals(caps.get("pushNotifications"));
        }

        return new AgentCardInfo(name, description, url, version, skillsList, streaming, push, raw);
    }

    public int size() { return agents.size(); }
}
