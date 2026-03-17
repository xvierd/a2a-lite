package com.a2alite;

import com.a2alite.errors.RemoteAgentException;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Logger;

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
    private Object extractResult(Map<String, Object> response) throws Exception {
        if (response.containsKey("error")) {
            var error = response.get("error");
            var message = error instanceof String ? (String) error : mapper.writeValueAsString(error);
            throw new RemoteAgentException(message, response);
        }

        var result = (Map<String, Object>) response.getOrDefault("result", Map.of());
        var parts = (List<Map<String, Object>>) result.getOrDefault("parts", List.of());

        for (var part : parts) {
            if ("text".equals(part.get("kind")) || "text".equals(part.get("type"))) {
                var text = (String) part.get("text");
                try {
                    return mapper.readValue(text, Object.class);
                } catch (Exception e) {
                    return text;
                }
            }
        }

        return result;
    }

    public int size() { return agents.size(); }
}
