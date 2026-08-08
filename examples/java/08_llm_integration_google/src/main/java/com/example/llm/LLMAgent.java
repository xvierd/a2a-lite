package com.example.llm;

import io.javalin.Javalin;
import io.javalin.http.Context;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.*;

/**
 * LLM Agent - A2A protocol v1.0 from scratch (Javalin + Jackson, no SDK)
 *
 * Advanced LLM-powered agent with OpenAI/Anthropic integration,
 * conversation memory, and tool calling capabilities.
 * Implements the A2A v1.0 wire protocol by hand — for the official
 * Java SDK approach see packages/java.
 *
 * COMPLEXITY: ~220 lines (compare with A2A Lite: ~50 lines)
 */
public class LLMAgent {

    private static final int PORT = 8793;
    private static final ObjectMapper mapper = new ObjectMapper();
    private static final String A2A_VERSION = "1.0";
    
    private final LLMClient llmClient;
    private final ConversationManager conversationMgr;
    private final ToolRegistry toolRegistry;
    
    public LLMAgent() {
        // Initialize components
        String provider = System.getenv().getOrDefault("LLM_PROVIDER", "openai");
        String model = System.getenv("LLM_MODEL");
        
        this.conversationMgr = new ConversationManager(10);
        this.toolRegistry = new ToolRegistry();
        this.llmClient = new LLMClient(provider, model);
        
        System.out.println("  ✓ LLM Client: " + provider + "/" + llmClient.getModel());
        System.out.println("  ✓ Conversation Manager: " + conversationMgr.getMaxHistory() + " messages");
        System.out.println("  ✓ Tools: " + String.join(", ", toolRegistry.getToolNames()));
    }
    
    public static void main(String[] args) {
        System.out.println("=".repeat(70));
        System.out.println("LLM Agent - A2A v1.0 from scratch (Java)");
        System.out.println("=".repeat(70));
        
        LLMAgent agent = new LLMAgent();
        agent.start();
    }
    
    public void start() {
        ObjectNode agentCard = createAgentCard();
        
        Javalin app = Javalin.create(config -> {
            config.showJavalinBanner = false;
        });
        
        // Agent card endpoint (A2A v1.0 discovery)
        app.get("/.well-known/agent-card.json", ctx -> {
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(agentCard));
        });
        
        // Health check
        app.get("/", ctx -> {
            ObjectNode health = mapper.createObjectNode();
            health.put("status", "healthy");
            health.put("agent", "LLMAgent");
            health.put("llm_ready", llmClient.isReady());
            ctx.json(health);
        });
        
        // Main A2A message endpoint
        app.post("/", ctx -> handleRequest(ctx));
        
        System.out.println("-".repeat(70));
        System.out.println("Starting server on http://localhost:" + PORT);
        System.out.println("Agent card: http://localhost:" + PORT + "/.well-known/agent-card.json");
        System.out.println("Skills: chat, clear_memory, info");
        System.out.println("=".repeat(70));
        
        app.start(PORT);
    }
    
    private void handleRequest(Context ctx) {
        try {
            // A2A v1.0: echo the protocol version on every response
            ctx.header("A2A-Version", A2A_VERSION);

            String body = ctx.body();
            ObjectNode request = (ObjectNode) mapper.readTree(body);

            // Validate JSON-RPC
            if (!request.has("jsonrpc") || !"2.0".equals(request.get("jsonrpc").asText())) {
                sendError(ctx, request.get("id"), -32600, "Invalid JSON-RPC request");
                return;
            }

            String method = request.has("method") ? request.get("method").asText() : "";
            if (!"SendMessage".equals(method)) {
                sendError(ctx, request.get("id"), -32601, "Method not found: " + method);
                return;
            }

            // Extract message
            JsonNode params = request.path("params");
            JsonNode message = params.path("message");
            String sessionId = params.path("sessionId").asText("default");

            // Extract skill call from message
            SkillCall skillCall = extractSkillCall(message);
            if (skillCall == null) {
                sendError(ctx, request.get("id"), -32602, "No skill call found in message");
                return;
            }

            // Execute skill
            Object result = executeSkill(skillCall, sessionId);

            // Build v1.0 response: {"result":{"message":{...}}}
            ObjectNode response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.set("id", request.get("id"));

            ObjectNode messageNode = mapper.createObjectNode();
            messageNode.put("messageId", java.util.UUID.randomUUID().toString());
            messageNode.put("role", "ROLE_AGENT");
            messageNode.putArray("parts").addObject()
                .put("text", mapper.writeValueAsString(result));

            ObjectNode resultNode = response.putObject("result");
            resultNode.set("message", messageNode);

            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(response));

        } catch (Exception e) {
            sendError(ctx, null, -32603, "Internal error: " + e.getMessage());
        }
    }
    
    private SkillCall extractSkillCall(JsonNode message) {
        JsonNode parts = message.path("parts");
        if (!parts.isArray() || parts.isEmpty()) {
            return null;
        }
        
        for (JsonNode part : parts) {
            // v1.0 parts: text parts are detected by the "text" field
            if (!part.has("text")) {
                continue;
            }
            String text = part.get("text").asText();
            if (text.isEmpty()) {
                continue;
            }
            
            try {
                ObjectNode parsed = (ObjectNode) mapper.readTree(text);
                String skill = parsed.path("skill").asText();
                JsonNode params = parsed.path("params");
                return new SkillCall(skill, params);
            } catch (Exception e) {
                // Treat as direct chat message
                ObjectNode params = mapper.createObjectNode();
                params.put("message", text);
                return new SkillCall("chat", params);
            }
        }
        return null;
    }
    
    private Object executeSkill(SkillCall skillCall, String sessionId) throws Exception {
        return switch (skillCall.skill()) {
            case "chat" -> handleChat(skillCall.params(), sessionId);
            case "clear_memory" -> handleClearMemory(sessionId);
            case "info" -> handleInfo();
            default -> Map.of("error", "Unknown skill: " + skillCall.skill());
        };
    }
    
    private Object handleChat(JsonNode params, String sessionId) throws Exception {
        if (!llmClient.isReady()) {
            return Map.of("error", "LLM not configured. Set OPENAI_API_KEY or ANTHROPIC_API_KEY.");
        }
        
        String userMessage = params.path("message").asText();
        if (userMessage.isEmpty()) {
            return Map.of("error", "No message provided");
        }
        
        // Add user message to history
        conversationMgr.addMessage(sessionId, "user", userMessage);
        
        // Get conversation history
        List<Map<String, String>> messages = conversationMgr.getMessages(sessionId);
        
        // Get available tools
        List<Map<String, Object>> tools = toolRegistry.getToolSchemas();
        
        // Call LLM
        LLMResponse response = llmClient.chat(messages, tools);
        
        // Handle tool calls if present
        if (response.toolCalls() != null && !response.toolCalls().isEmpty()) {
            // Add assistant message with tool calls
            conversationMgr.addMessage(sessionId, "assistant", response.content(), 
                Map.of("tool_calls", response.toolCalls()));
            
            // Execute tools
            for (ToolCall tc : response.toolCalls()) {
                String result = toolRegistry.execute(tc.name(), tc.arguments());
                conversationMgr.addMessage(sessionId, "user", result, 
                    Map.of("tool_result", true, "name", tc.name()));
            }
            
            // Get final response
            messages = conversationMgr.getMessages(sessionId);
            response = llmClient.chat(messages, null);
        }
        
        // Add assistant response to history
        conversationMgr.addMessage(sessionId, "assistant", response.content());
        
        return Map.of(
            "response", response.content(),
            "session_id", sessionId,
            "history_length", conversationMgr.getHistoryLength(sessionId)
        );
    }
    
    private Object handleClearMemory(String sessionId) {
        conversationMgr.clearSession(sessionId);
        return Map.of(
            "message", "Memory cleared",
            "session_id", sessionId
        );
    }
    
    private Object handleInfo() {
        return Map.of(
            "name", "LLMAgent",
            "description", "AI agent with OpenAI/Anthropic LLM integration",
            "version", "1.0.0",
            "llm_provider", llmClient.getProvider(),
            "llm_model", llmClient.getModel(),
            "llm_ready", llmClient.isReady(),
            "skills", List.of("chat", "clear_memory", "info"),
            "tools_available", toolRegistry.getToolNames(),
            "features", List.of("memory", "tool_calling", "multi_turn")
        );
    }
    
    private ObjectNode createAgentCard() {
        ObjectNode card = mapper.createObjectNode();
        card.put("name", "LLMAgent");
        card.put("description", "AI agent powered by OpenAI/Anthropic with memory and tools");
        card.put("version", "1.0.0");

        // v1.0: interfaces replace the root "url" field
        ArrayNode interfaces = card.putArray("supportedInterfaces");
        interfaces.addObject()
            .put("url", "http://localhost:" + PORT + "/")
            .put("protocolBinding", "JSONRPC")
            .put("protocolVersion", "1.0");

        // Capabilities
        ObjectNode capabilities = card.putObject("capabilities");
        capabilities.put("streaming", false);
        capabilities.put("pushNotifications", false);

        // Skills
        ArrayNode skills = card.putArray("skills");

        // Chat skill
        ObjectNode chatSkill = skills.addObject();
        chatSkill.put("id", "chat");
        chatSkill.put("name", "chat");
        chatSkill.put("description", "Chat with AI assistant with memory");
        chatSkill.putArray("tags").add("conversation").add("llm");

        // Clear memory skill
        ObjectNode clearSkill = skills.addObject();
        clearSkill.put("id", "clear_memory");
        clearSkill.put("name", "clear_memory");
        clearSkill.put("description", "Clear conversation memory");
        clearSkill.putArray("tags").add("memory").add("reset");

        // Info skill
        ObjectNode infoSkill = skills.addObject();
        infoSkill.put("id", "info");
        infoSkill.put("name", "info");
        infoSkill.put("description", "Get agent information");
        infoSkill.putArray("tags").add("info").add("metadata");

        card.putArray("defaultInputModes").add("text/plain");
        card.putArray("defaultOutputModes").add("text/plain");

        return card;
    }
    
    private void sendError(Context ctx, JsonNode id, int code, String message) {
        try {
            ObjectNode error = mapper.createObjectNode();
            error.put("jsonrpc", "2.0");
            if (id != null) {
                error.set("id", id);
            } else {
                error.putNull("id");
            }
            ObjectNode errorObj = mapper.createObjectNode();
            errorObj.put("code", code);
            errorObj.put("message", message);
            error.set("error", errorObj);
            
            ctx.status(400);
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(error));
        } catch (Exception e) {
            ctx.status(500);
            ctx.result("Internal error");
        }
    }
}

// Record for skill calls
record SkillCall(String skill, JsonNode params) {}

// Record for LLM tool calls
record ToolCall(String name, Map<String, Object> arguments, String id) {}

// Record for LLM responses
record LLMResponse(String content, List<ToolCall> toolCalls) {
    public LLMResponse(String content) {
        this(content, null);
    }
}
