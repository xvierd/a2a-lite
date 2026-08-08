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
    /** A2A protocol version header sent on every JSON-RPC POST (required by A2A v1.0 servers). */
    private static final String A2A_VERSION_HEADER = "A2A-Version";
    private static final String A2A_VERSION = "1.0";
    private static final Set<String> TERMINAL_STATES = Set.of(
        "TASK_STATE_COMPLETED", "TASK_STATE_FAILED", "TASK_STATE_CANCELED", "TASK_STATE_REJECTED");
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
     * fetched from {@code url/.well-known/agent-card.json} and cached.
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
     * <p>Sends a {@code GetTask} JSON-RPC request to the given agent URL.
     */
    public Object getRemoteTask(String agentUrl, String taskId, int timeoutSeconds) throws Exception {
        var requestBody = mapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0",
            "method", "GetTask",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of("id", taskId)
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .header(A2A_VERSION_HEADER, A2A_VERSION)
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
     * <p>Sends a {@code CancelTask} JSON-RPC request to the given agent URL.
     */
    public Object cancelRemoteTask(String agentUrl, String taskId, int timeoutSeconds) throws Exception {
        var requestBody = mapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0",
            "method", "CancelTask",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of("id", taskId)
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .header(A2A_VERSION_HEADER, A2A_VERSION)
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
     * {@code agentUrl/.well-known/agent-card.json}.
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
            .uri(URI.create(cleanUrl + "/.well-known/agent-card.json"))
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
                    "method", "SendStreamingMessage",
                    "id", UUID.randomUUID().toString().replace("-", ""),
                    "params", Map.of(
                        "message", Map.of(
                            "role", "ROLE_USER",
                            "parts", List.of(Map.of("text", message)),
                            "messageId", UUID.randomUUID().toString().replace("-", "")
                        )
                    )
                ));

                var request = HttpRequest.newBuilder()
                    .uri(URI.create(agentUrl))
                    .header("Content-Type", "application/json")
                    .header("Accept", "text/event-stream")
                    .header(A2A_VERSION_HEADER, A2A_VERSION)
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
                        var data = (Map<String, Object>) mapper.readValue(json, Map.class);

                        // A2A v1.0 SSE events: {"result": {"task"|"statusUpdate"|"artifactUpdate"|"message": ...}}
                        @SuppressWarnings("unchecked")
                        var event = (Map<String, Object>) data.getOrDefault("result", data);

                        // Task status, from a statusUpdate event or the initial task event
                        Map<String, Object> status = null;
                        if (event.get("statusUpdate") instanceof Map<?, ?> su) {
                            @SuppressWarnings("unchecked")
                            var s = (Map<String, Object>) ((Map<String, Object>) su).get("status");
                            status = s;
                        } else if (event.get("task") instanceof Map<?, ?> t) {
                            @SuppressWarnings("unchecked")
                            var s = (Map<String, Object>) ((Map<String, Object>) t).get("status");
                            status = s;
                        }

                        var state = status != null ? (String) status.get("state") : null;

                        // Check for failed status
                        if ("TASK_STATE_FAILED".equals(state)) {
                            throw new RemoteAgentException(
                                "Remote agent task failed", event);
                        }

                        // Extract text chunks from artifact updates
                        if (event.get("artifactUpdate") instanceof Map<?, ?> au) {
                            @SuppressWarnings("unchecked")
                            var artifact = (Map<String, Object>) ((Map<String, Object>) au).get("artifact");
                            if (artifact != null) {
                                putTextParts(artifact, queue);
                            }
                        }

                        // Extract text chunks from status update messages
                        if (status != null && status.get("message") instanceof Map<?, ?> sm) {
                            @SuppressWarnings("unchecked")
                            var statusMessage = (Map<String, Object>) sm;
                            putTextParts(statusMessage, queue);
                        }

                        // Extract text chunks from a direct message event
                        if (event.get("message") instanceof Map<?, ?> m) {
                            @SuppressWarnings("unchecked")
                            var messageEvent = (Map<String, Object>) m;
                            putTextParts(messageEvent, queue);
                        }

                        // Stop on terminal state (stream end also terminates the loop)
                        if (state != null && TERMINAL_STATES.contains(state)) {
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
        var params = new HashMap<String, Object>();
        params.put("taskId", taskId);
        params.put("url", webhookUrl);
        if (token != null) {
            params.put("token", token);
        }

        var requestBody = mapper.writeValueAsString(Map.of(
            "jsonrpc", "2.0",
            "method", "CreateTaskPushNotificationConfig",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", params
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .header(A2A_VERSION_HEADER, A2A_VERSION)
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
            "method", "GetTaskPushNotificationConfig",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of("taskId", taskId)
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .header(A2A_VERSION_HEADER, A2A_VERSION)
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
            "method", "DeleteTaskPushNotificationConfig",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of("taskId", taskId)
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .header(A2A_VERSION_HEADER, A2A_VERSION)
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
            "method", "SendMessage",
            "id", UUID.randomUUID().toString().replace("-", ""),
            "params", Map.of(
                "message", Map.of(
                    "role", "ROLE_USER",
                    "parts", List.of(Map.of("text", message)),
                    "messageId", UUID.randomUUID().toString().replace("-", "")
                )
            )
        ));

        var request = HttpRequest.newBuilder()
            .uri(URI.create(agentUrl))
            .header("Content-Type", "application/json")
            .header(A2A_VERSION_HEADER, A2A_VERSION)
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

        // A2A v1.0: result is { message: {...} } or { task: {...} }
        var envelope = (Map<String, Object>) response.getOrDefault("result", Map.of());
        var result = envelope.get("message") instanceof Map<?, ?> m ? (Map<String, Object>) m
            : envelope.get("task") instanceof Map<?, ?> t ? (Map<String, Object>) t
            : envelope;

        // Task ID from the v1.0 response envelope:
        // result.task.id, result.message.taskId, or result.id (bare Task)
        String taskId = null;
        if (envelope.get("task") instanceof Map<?, ?> taskObj && ((Map<String, Object>) taskObj).get("id") != null) {
            taskId = String.valueOf(((Map<String, Object>) taskObj).get("id"));
        } else if (envelope.get("message") instanceof Map<?, ?> msgObj && ((Map<String, Object>) msgObj).get("taskId") != null) {
            taskId = String.valueOf(((Map<String, Object>) msgObj).get("taskId"));
        } else if (envelope.get("id") != null) {
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

    /**
     * Pushes the text of every text part of a message/artifact-like map onto the queue.
     */
    @SuppressWarnings("unchecked")
    private static void putTextParts(Map<String, Object> container, java.util.concurrent.BlockingQueue<Object> queue) throws InterruptedException {
        if (container.get("parts") instanceof List<?> parts) {
            for (var part : parts) {
                if (part instanceof Map<?, ?> partMap && ((Map<String, Object>) partMap).get("text") instanceof String text) {
                    queue.put(text);
                }
            }
        }
    }

    private Object parseJsonOrText(String text) {
        try {
            return mapper.readValue(text, Object.class);
        } catch (Exception e) {
            return text;
        }
    }

    @SuppressWarnings("unchecked")
    AgentCardInfo parseAgentCard(Map<String, Object> raw) {
        // Detect A2A 0.3 cards: root `url`/`protocolVersion` without `supportedInterfaces`
        if (!raw.containsKey("supportedInterfaces")
                && (raw.containsKey("url") || raw.containsKey("protocolVersion"))) {
            throw new IllegalArgumentException(
                "Remote agent speaks A2A 0.3, not supported by a2a-lite 1.0");
        }

        var name = (String) raw.getOrDefault("name", "");
        var description = (String) raw.getOrDefault("description", "");
        var version = (String) raw.getOrDefault("version", "");

        // A2A v1.0: the endpoint URL lives in supportedInterfaces[0].url
        var url = "";
        if (raw.get("supportedInterfaces") instanceof List<?> interfaces && !interfaces.isEmpty()) {
            var first = interfaces.get(0);
            if (first instanceof Map<?, ?> iface) {
                url = (String) ((Map<String, Object>) iface).getOrDefault("url", "");
            }
        }

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
