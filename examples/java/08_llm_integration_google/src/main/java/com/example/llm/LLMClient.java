package com.example.llm;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.JsonNode;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.*;

/**
 * LLM Client for OpenAI and Anthropic APIs.
 * 
 * Handles chat completions and tool calling for both providers.
 * COMPLEXITY: ~180 lines
 */
public class LLMClient {
    
    private static final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient httpClient;
    
    private final String provider;
    private final String model;
    private final String apiKey;
    private final boolean ready;
    
    public LLMClient(String provider, String model) {
        this.provider = provider.toLowerCase();
        this.httpClient = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(30))
            .build();
        
        // Initialize based on provider
        switch (this.provider) {
            case "openai" -> {
                this.apiKey = System.getenv("OPENAI_API_KEY");
                this.model = model != null ? model : "gpt-4";
                this.ready = this.apiKey != null;
                if (!ready) {
                    System.err.println("  ⚠ OPENAI_API_KEY not set");
                }
            }
            case "anthropic" -> {
                this.apiKey = System.getenv("ANTHROPIC_API_KEY");
                this.model = model != null ? model : "claude-3-sonnet-20240229";
                this.ready = this.apiKey != null;
                if (!ready) {
                    System.err.println("  ⚠ ANTHROPIC_API_KEY not set");
                }
            }
            default -> throw new IllegalArgumentException("Unknown provider: " + provider);
        }
    }
    
    public boolean isReady() {
        return ready;
    }
    
    public String getProvider() {
        return provider;
    }
    
    public String getModel() {
        return model;
    }
    
    public LLMResponse chat(List<Map<String, String>> messages, 
                            List<Map<String, Object>> tools) throws Exception {
        return switch (provider) {
            case "openai" -> openaiChat(messages, tools);
            case "anthropic" -> anthropicChat(messages, tools);
            default -> throw new IllegalStateException("Unknown provider: " + provider);
        };
    }
    
    private LLMResponse openaiChat(List<Map<String, String>> messages,
                                    List<Map<String, Object>> tools) throws Exception {
        ObjectNode body = mapper.createObjectNode();
        body.put("model", model);
        body.put("temperature", 0.7);
        body.put("max_tokens", 1000);
        
        // Add messages
        ArrayNode messagesArray = body.putArray("messages");
        for (Map<String, String> msg : messages) {
            ObjectNode msgNode = messagesArray.addObject();
            msgNode.put("role", msg.get("role"));
            msgNode.put("content", msg.get("content"));
        }
        
        // Add tools if provided
        if (tools != null && !tools.isEmpty()) {
            ArrayNode toolsArray = body.putArray("tools");
            for (Map<String, Object> tool : tools) {
                ObjectNode toolNode = toolsArray.addObject();
                toolNode.put("type", "function");
                ObjectNode functionNode = toolNode.putObject("function");
                functionNode.put("name", (String) tool.get("name"));
                functionNode.put("description", (String) tool.get("description"));
                functionNode.set("parameters", mapper.valueToTree(tool.get("parameters")));
            }
            body.put("tool_choice", "auto");
        }
        
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.openai.com/v1/chat/completions"))
            .header("Content-Type", "application/json")
            .header("Authorization", "Bearer " + apiKey)
            .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
            .build();
        
        HttpResponse<String> response = httpClient.send(request, 
            HttpResponse.BodyHandlers.ofString());
        
        if (response.statusCode() != 200) {
            throw new RuntimeException("OpenAI API error: " + response.body());
        }
        
        JsonNode json = mapper.readTree(response.body());
        JsonNode choice = json.get("choices").get(0);
        JsonNode message = choice.get("message");
        
        String content = message.path("content").asText("");
        
        // Check for tool calls
        List<ToolCall> toolCalls = null;
        if (message.has("tool_calls")) {
            toolCalls = new ArrayList<>();
            for (JsonNode tc : message.get("tool_calls")) {
                String name = tc.path("function").path("name").asText();
                String argsStr = tc.path("function").path("arguments").asText();
                Map<String, Object> args = mapper.readValue(argsStr, Map.class);
                String id = tc.path("id").asText();
                toolCalls.add(new ToolCall(name, args, id));
            }
        }
        
        return new LLMResponse(content, toolCalls);
    }
    
    private LLMResponse anthropicChat(List<Map<String, String>> messages,
                                       List<Map<String, Object>> tools) throws Exception {
        // Separate system message from chat messages
        String systemMessage = null;
        List<Map<String, String>> chatMessages = new ArrayList<>();
        
        for (Map<String, String> msg : messages) {
            if ("system".equals(msg.get("role"))) {
                systemMessage = msg.get("content");
            } else {
                Map<String, String> chatMsg = new HashMap<>();
                chatMsg.put("role", msg.get("role"));
                chatMsg.put("content", msg.get("content"));
                chatMessages.add(chatMsg);
            }
        }
        
        ObjectNode body = mapper.createObjectNode();
        body.put("model", model);
        body.put("max_tokens", 1000);
        body.put("temperature", 0.7);
        
        if (systemMessage != null) {
            body.put("system", systemMessage);
        }
        
        // Add messages
        ArrayNode messagesArray = body.putArray("messages");
        for (Map<String, String> msg : chatMessages) {
            ObjectNode msgNode = messagesArray.addObject();
            String role = msg.get("role");
            // Map 'assistant' to 'assistant' for Anthropic
            msgNode.put("role", role.equals("assistant") ? "assistant" : "user");
            msgNode.put("content", msg.get("content"));
        }
        
        // Add tools if provided (Anthropic format)
        if (tools != null && !tools.isEmpty()) {
            ArrayNode toolsArray = body.putArray("tools");
            for (Map<String, Object> tool : tools) {
                ObjectNode toolNode = toolsArray.addObject();
                toolNode.put("name", (String) tool.get("name"));
                toolNode.put("description", (String) tool.get("description"));
                toolNode.set("input_schema", mapper.valueToTree(tool.get("parameters")));
            }
        }
        
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://api.anthropic.com/v1/messages"))
            .header("Content-Type", "application/json")
            .header("x-api-key", apiKey)
            .header("anthropic-version", "2023-06-01")
            .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
            .build();
        
        HttpResponse<String> response = httpClient.send(request, 
            HttpResponse.BodyHandlers.ofString());
        
        if (response.statusCode() != 200) {
            throw new RuntimeException("Anthropic API error: " + response.body());
        }
        
        JsonNode json = mapper.readTree(response.body());
        
        StringBuilder content = new StringBuilder();
        List<ToolCall> toolCalls = null;
        
        for (JsonNode block : json.get("content")) {
            String type = block.path("type").asText();
            if ("text".equals(type)) {
                content.append(block.path("text").asText());
            } else if ("tool_use".equals(type)) {
                if (toolCalls == null) {
                    toolCalls = new ArrayList<>();
                }
                String name = block.path("name").asText();
                Map<String, Object> args = mapper.convertValue(block.path("input"), Map.class);
                String id = block.path("id").asText();
                toolCalls.add(new ToolCall(name, args, id));
            }
        }
        
        return new LLMResponse(content.toString(), toolCalls);
    }
}
