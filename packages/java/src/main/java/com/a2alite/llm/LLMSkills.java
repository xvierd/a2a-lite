package com.a2alite.llm;

import com.a2alite.SkillHandler;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Factory methods for LLM-backed skill handlers.
 *
 * Each method returns a {@link SkillHandler} that calls an LLM API.
 * The first string parameter of the skill is used as the user message.
 *
 * <pre>{@code
 * agent.skill("chat", LLMSkills.openai("gpt-4o-mini"));
 * agent.skill("analyze", LLMSkills.anthropic("claude-sonnet-4-6"));
 * agent.skill("local", LLMSkills.ollama("llama3.2"));
 * }</pre>
 *
 * OpenAI and Anthropic use their respective REST APIs directly (no SDK needed).
 * Set the API key via environment variable:
 * <ul>
 *   <li>OpenAI: OPENAI_API_KEY</li>
 *   <li>Anthropic: ANTHROPIC_API_KEY</li>
 * </ul>
 *
 * Ollama uses the local HTTP API (no auth needed).
 */
public class LLMSkills {
    private static final HttpClient HTTP = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10))
        .build();
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private LLMSkills() {}

    // ── OpenAI ──────────────────────────────────────────────────────────────

    /**
     * Creates a skill handler that calls the OpenAI chat completions API.
     *
     * Requires: OPENAI_API_KEY environment variable.
     *
     * @param model OpenAI model ID (e.g., "gpt-4o-mini", "gpt-4o")
     */
    public static SkillHandler openai(String model) {
        return openai(model, "You are a helpful assistant.", 0.7, null);
    }

    /**
     * Creates a skill handler for OpenAI with full configuration.
     *
     * @param model        OpenAI model ID
     * @param systemPrompt System message
     * @param temperature  Sampling temperature (0.0-2.0)
     * @param maxTokens    Max response tokens (null = model default)
     */
    public static SkillHandler openai(String model, String systemPrompt, double temperature, Integer maxTokens) {
        return params -> {
            var apiKey = System.getenv("OPENAI_API_KEY");
            if (apiKey == null || apiKey.isBlank()) {
                throw new IllegalStateException("OPENAI_API_KEY environment variable is not set");
            }

            var userMessage = extractUserMessage(params);
            var requestBody = new HashMap<String, Object>();
            requestBody.put("model", model);
            requestBody.put("temperature", temperature);
            requestBody.put("messages", List.of(
                Map.of("role", "system", "content", systemPrompt),
                Map.of("role", "user", "content", userMessage)
            ));
            if (maxTokens != null) requestBody.put("max_tokens", maxTokens);

            var request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.openai.com/v1/chat/completions"))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .POST(HttpRequest.BodyPublishers.ofString(MAPPER.writeValueAsString(requestBody)))
                .timeout(Duration.ofSeconds(60))
                .build();

            var response = HTTP.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new RuntimeException("OpenAI API error: HTTP " + response.statusCode() + ": " + response.body());
            }

            @SuppressWarnings("unchecked")
            var data = (Map<String, Object>) MAPPER.readValue(response.body(), Map.class);
            @SuppressWarnings("unchecked")
            var choices = (List<Map<String, Object>>) data.get("choices");
            if (choices == null || choices.isEmpty()) return "";
            @SuppressWarnings("unchecked")
            var message = (Map<String, Object>) choices.get(0).get("message");
            return message != null ? (String) message.get("content") : "";
        };
    }

    // ── Anthropic ───────────────────────────────────────────────────────────

    /**
     * Creates a skill handler that calls the Anthropic messages API.
     *
     * Requires: ANTHROPIC_API_KEY environment variable.
     *
     * @param model Anthropic model ID (e.g., "claude-sonnet-4-6", "claude-haiku-4-5-20251001")
     */
    public static SkillHandler anthropic(String model) {
        return anthropic(model, "You are a helpful assistant.", 0.7, 1024);
    }

    /**
     * Creates a skill handler for Anthropic with full configuration.
     *
     * @param model        Anthropic model ID
     * @param systemPrompt System message
     * @param temperature  Sampling temperature (0.0-1.0)
     * @param maxTokens    Max response tokens
     */
    public static SkillHandler anthropic(String model, String systemPrompt, double temperature, int maxTokens) {
        return params -> {
            var apiKey = System.getenv("ANTHROPIC_API_KEY");
            if (apiKey == null || apiKey.isBlank()) {
                throw new IllegalStateException("ANTHROPIC_API_KEY environment variable is not set");
            }

            var userMessage = extractUserMessage(params);
            var requestBody = Map.of(
                "model", model,
                "max_tokens", maxTokens,
                "temperature", temperature,
                "system", systemPrompt,
                "messages", List.of(Map.of("role", "user", "content", userMessage))
            );

            var request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.anthropic.com/v1/messages"))
                .header("Content-Type", "application/json")
                .header("x-api-key", apiKey)
                .header("anthropic-version", "2023-06-01")
                .POST(HttpRequest.BodyPublishers.ofString(MAPPER.writeValueAsString(requestBody)))
                .timeout(Duration.ofSeconds(60))
                .build();

            var response = HTTP.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new RuntimeException("Anthropic API error: HTTP " + response.statusCode() + ": " + response.body());
            }

            @SuppressWarnings("unchecked")
            var data = (Map<String, Object>) MAPPER.readValue(response.body(), Map.class);
            @SuppressWarnings("unchecked")
            var content = (List<Map<String, Object>>) data.get("content");
            if (content == null || content.isEmpty()) return "";
            var sb = new StringBuilder();
            for (var block : content) {
                if ("text".equals(block.get("type"))) {
                    sb.append(block.get("text"));
                }
            }
            return sb.toString();
        };
    }

    // ── Ollama ──────────────────────────────────────────────────────────────

    /**
     * Creates a skill handler that calls a local Ollama instance.
     *
     * No API key or extra dependencies needed.
     *
     * @param model Ollama model name (e.g., "llama3.2", "mistral", "phi3")
     */
    public static SkillHandler ollama(String model) {
        return ollama(model, "http://localhost:11434", "You are a helpful assistant.", 0.7);
    }

    /**
     * Creates a skill handler for Ollama with full configuration.
     *
     * @param model        Ollama model name
     * @param baseUrl      Ollama server URL (default: http://localhost:11434)
     * @param systemPrompt System message
     * @param temperature  Sampling temperature
     */
    public static SkillHandler ollama(String model, String baseUrl, String systemPrompt, double temperature) {
        return params -> {
            var userMessage = extractUserMessage(params);
            var requestBody = Map.of(
                "model", model,
                "stream", false,
                "messages", List.of(
                    Map.of("role", "system", "content", systemPrompt),
                    Map.of("role", "user", "content", userMessage)
                ),
                "options", Map.of("temperature", temperature)
            );

            var url = baseUrl.replaceAll("/$", "") + "/api/chat";
            var request = HttpRequest.newBuilder()
                .uri(URI.create(url))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(MAPPER.writeValueAsString(requestBody)))
                .timeout(Duration.ofSeconds(120))
                .build();

            var response = HTTP.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new RuntimeException("Ollama error: HTTP " + response.statusCode() + ": " + response.body());
            }

            @SuppressWarnings("unchecked")
            var data = (Map<String, Object>) MAPPER.readValue(response.body(), Map.class);
            @SuppressWarnings("unchecked")
            var message = (Map<String, Object>) data.get("message");
            return message != null ? (String) message.get("content") : "";
        };
    }

    // ── Bedrock ─────────────────────────────────────────────────────────────

    /**
     * Creates a skill handler that calls the AWS Bedrock InvokeModel API.
     *
     * Uses the Anthropic Messages API format (works with Claude models on Bedrock).
     * AWS credentials are loaded from the default credential chain.
     *
     * Requires: {@code software.amazon.awssdk:bedrockruntime} on the classpath.
     *
     * <pre>{@code
     * agent.skill("chat", LLMSkills.bedrock("anthropic.claude-3-haiku-20240307-v1:0"));
     * }</pre>
     *
     * @param model Bedrock model ID
     */
    public static SkillHandler bedrock(String model) {
        return bedrock(model, "us-east-1", "You are a helpful assistant.", 0.7, 1024);
    }

    /**
     * Creates a skill handler for Bedrock with full configuration.
     *
     * @param model        Bedrock model ID
     * @param region       AWS region
     * @param systemPrompt System message
     * @param temperature  Sampling temperature
     * @param maxTokens    Maximum tokens in the response
     */
    public static SkillHandler bedrock(String model, String region, String systemPrompt,
                                        double temperature, int maxTokens) {
        return params -> {
            try {
                var userMessage = extractUserMessage(params);

                // Build the request payload (Anthropic Messages API format for Claude models)
                var payload = new HashMap<String, Object>();
                payload.put("anthropic_version", "bedrock-2023-05-31");
                payload.put("max_tokens", maxTokens);
                payload.put("temperature", temperature);
                payload.put("system", systemPrompt);
                payload.put("messages", List.of(
                    Map.of("role", "user", "content", userMessage)
                ));

                var bodyBytes = software.amazon.awssdk.core.SdkBytes.fromUtf8String(
                    MAPPER.writeValueAsString(payload));

                var client = software.amazon.awssdk.services.bedrockruntime.BedrockRuntimeClient.builder()
                    .region(software.amazon.awssdk.regions.Region.of(region))
                    .build();

                var request = software.amazon.awssdk.services.bedrockruntime.model.InvokeModelRequest.builder()
                    .modelId(model)
                    .contentType("application/json")
                    .accept("application/json")
                    .body(bodyBytes)
                    .build();

                var response = client.invokeModel(request);

                @SuppressWarnings("unchecked")
                var data = (Map<String, Object>) MAPPER.readValue(
                    response.body().asUtf8String(), Map.class);

                // Parse Anthropic-style response
                @SuppressWarnings("unchecked")
                var content = (List<Map<String, Object>>) data.get("content");
                if (content == null || content.isEmpty()) return "";
                var sb = new StringBuilder();
                for (var block : content) {
                    if ("text".equals(block.get("type"))) {
                        sb.append(block.get("text"));
                    }
                }
                return sb.toString();

            } catch (NoClassDefFoundError | UnsupportedClassVersionError e) {
                throw new RuntimeException(
                    "Bedrock requires 'software.amazon.awssdk:bedrockruntime'. " +
                    "Add to your build: implementation 'software.amazon.awssdk:bedrockruntime:2.31.3'", e);
            }
        };
    }

    // ── Helper ──────────────────────────────────────────────────────────────

    private static String extractUserMessage(Map<String, Object> params) {
        for (var key : List.of("message", "text", "query", "prompt", "input")) {
            if (params.containsKey(key)) {
                return String.valueOf(params.get(key));
            }
        }
        var first = params.values().stream().findFirst();
        return first.map(String::valueOf).orElse("");
    }
}
