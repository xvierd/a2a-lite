package com.example.streaming;

import io.javalin.Javalin;
import io.javalin.http.Context;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.example.streaming.sse.SseEventEmitter;
import com.example.streaming.skills.*;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Streaming Agent - Google A2A SDK Implementation (Java)
 * 
 * Demonstrates Server-Sent Events (SSE) streaming with the official Google A2A SDK.
 * Shows full control over streaming infrastructure but requires significant boilerplate.
 * 
 * Features:
 * - AgentCapabilities with streaming=true
 * - SSE streaming infrastructure
 * - Multiple streaming skills: chat, count, story, progress
 * - Manual event management and client tracking
 */
public class StreamingAgent {
    
    private static final int PORT = 8787;
    private static final ObjectMapper mapper = new ObjectMapper();
    
    // Active SSE connections for streaming
    private static final Map<String, SseEventEmitter> activeStreams = new ConcurrentHashMap<>();
    
    // Skill handlers
    private static final ChatSkill chatSkill = new ChatSkill();
    private static final CountSkill countSkill = new CountSkill();
    private static final StorySkill storySkill = new StorySkill();
    private static final ProgressSkill progressSkill = new ProgressSkill();
    
    public static void main(String[] args) {
        System.out.println("=".repeat(70));
        System.out.println("Streaming Agent - Google A2A SDK (Java)");
        System.out.println("=".repeat(70));
        
        // Create agent card with streaming capabilities
        ObjectNode agentCard = createAgentCard();
        
        // Setup Javalin server
        Javalin app = Javalin.create(config -> {
            config.showJavalinBanner = false;
        });
        
        // Agent card endpoint (A2A discovery)
        app.get("/.well-known/agent.json", ctx -> {
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(agentCard));
        });
        
        // Health check
        app.get("/", ctx -> {
            ObjectNode health = mapper.createObjectNode();
            health.put("status", "healthy");
            health.put("agent", "StreamingAgent");
            health.put("streaming", true);
            ctx.json(health);
        });
        
        // SSE endpoint for streaming
        app.get("/stream/{taskId}", ctx -> {
            handleSseConnection(ctx);
        });
        
        // Main A2A message endpoint (non-streaming)
        app.post("/", ctx -> {
            handleMessage(ctx);
        });
        
        // Streaming message endpoint
        app.post("/stream", ctx -> {
            handleStreamingRequest(ctx);
        });
        
        System.out.println("Agent: StreamingAgent");
        System.out.println("Skills: chat, count, story, progress");
        System.out.println("Capabilities: streaming=true");
        System.out.println("-".repeat(70));
        System.out.println("Starting server on http://localhost:" + PORT);
        System.out.println("Agent card: http://localhost:" + PORT + "/.well-known/agent.json");
        System.out.println("SSE endpoint: http://localhost:" + PORT + "/stream/{taskId}");
        System.out.println("=".repeat(70));
        
        app.start(PORT);
    }
    
    /**
     * Create the agent card with streaming capabilities.
     */
    private static ObjectNode createAgentCard() {
        ObjectNode card = mapper.createObjectNode();
        card.put("name", "StreamingAgent");
        card.put("description", "Streaming agent demonstrating SSE with Google A2A SDK");
        card.put("version", "1.0.0");
        card.put("url", "http://localhost:" + PORT + "/");
        
        // Skills array with streaming support
        ArrayNode skills = mapper.createArrayNode();
        skills.add(createSkillCard("chat", "Interactive chat with streaming responses",
            createChatSchema()));
        skills.add(createSkillCard("count", "Count to a number with progress updates",
            createCountSchema()));
        skills.add(createSkillCard("story", "Generate a story word by word",
            createStorySchema()));
        skills.add(createSkillCard("progress", "Show progress updates for long tasks",
            createProgressSchema()));
        card.set("skills", skills);
        
        // Capabilities - IMPORTANT: streaming=true
        ObjectNode capabilities = mapper.createObjectNode();
        capabilities.put("streaming", true);
        capabilities.put("pushNotifications", false);
        capabilities.put("stateTransitionHistory", false);
        card.set("capabilities", capabilities);
        
        return card;
    }
    
    private static ObjectNode createSkillCard(String name, String description, ObjectNode schema) {
        ObjectNode skill = mapper.createObjectNode();
        skill.put("name", name);
        skill.put("description", description);
        skill.set("inputSchema", schema);
        
        ObjectNode outputSchema = mapper.createObjectNode();
        outputSchema.put("type", "object");
        skill.set("outputSchema", outputSchema);
        
        return skill;
    }
    
    private static ObjectNode createChatSchema() {
        ObjectNode schema = mapper.createObjectNode();
        schema.put("type", "object");
        ObjectNode props = mapper.createObjectNode();
        ObjectNode msgProp = mapper.createObjectNode();
        msgProp.put("type", "string");
        msgProp.put("description", "Message to send");
        props.set("message", msgProp);
        schema.set("properties", props);
        ArrayNode required = mapper.createArrayNode();
        required.add("message");
        schema.set("required", required);
        return schema;
    }
    
    private static ObjectNode createCountSchema() {
        ObjectNode schema = mapper.createObjectNode();
        schema.put("type", "object");
        ObjectNode props = mapper.createObjectNode();
        ObjectNode toProp = mapper.createObjectNode();
        toProp.put("type", "integer");
        toProp.put("description", "Count up to this number");
        props.set("to", toProp);
        schema.set("properties", props);
        ArrayNode required = mapper.createArrayNode();
        required.add("to");
        schema.set("required", required);
        return schema;
    }
    
    private static ObjectNode createStorySchema() {
        ObjectNode schema = mapper.createObjectNode();
        schema.put("type", "object");
        ObjectNode props = mapper.createObjectNode();
        ObjectNode themeProp = mapper.createObjectNode();
        themeProp.put("type", "string");
        themeProp.put("description", "Story theme or topic");
        props.set("theme", themeProp);
        schema.set("properties", props);
        ArrayNode required = mapper.createArrayNode();
        required.add("theme");
        schema.set("required", required);
        return schema;
    }
    
    private static ObjectNode createProgressSchema() {
        ObjectNode schema = mapper.createObjectNode();
        schema.put("type", "object");
        ObjectNode props = mapper.createObjectNode();
        ObjectNode stepsProp = mapper.createObjectNode();
        stepsProp.put("type", "integer");
        stepsProp.put("description", "Number of progress steps");
        props.set("steps", stepsProp);
        schema.set("properties", props);
        ArrayNode required = mapper.createArrayNode();
        required.add("steps");
        schema.set("required", required);
        return schema;
    }
    
    /**
     * Handle SSE connection for streaming.
     */
    private static void handleSseConnection(Context ctx) {
        String taskId = ctx.pathParam("taskId");
        
        ctx.header("Content-Type", "text/event-stream");
        ctx.header("Cache-Control", "no-cache");
        ctx.header("Connection", "keep-alive");
        ctx.header("X-Accel-Buffering", "no"); // Disable nginx buffering
        
        SseEventEmitter emitter = new SseEventEmitter(ctx);
        activeStreams.put(taskId, emitter);
        
        System.out.println("[SSE] Client connected: " + taskId);
        
        // Send initial connected event
        emitter.sendEvent("connected", createStatusEvent("connected", "Stream established"));
        
        // Keep connection alive
        ctx.async(() -> {
            try {
                while (!emitter.isClosed()) {
                    Thread.sleep(1000);
                    emitter.sendEvent("ping", createStatusEvent("ping", "Keepalive"));
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });
    }
    
    /**
     * Handle non-streaming message requests.
     */
    private static void handleMessage(Context ctx) {
        try {
            String body = ctx.body();
            ObjectNode request = (ObjectNode) mapper.readTree(body);
            
            // Validate JSON-RPC
            if (!request.has("jsonrpc") || !"2.0".equals(request.get("jsonrpc").asText())) {
                sendError(ctx, request.get("id"), -32600, "Invalid JSON-RPC request");
                return;
            }
            
            String method = request.has("method") ? request.get("method").asText() : "";
            if (!"message/send".equals(method)) {
                sendError(ctx, request.get("id"), -32601, "Method not found: " + method);
                return;
            }
            
            // Process message synchronously
            ObjectNode response = processMessage(request);
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(response));
            
        } catch (Exception e) {
            sendError(ctx, null, -32603, "Internal error: " + e.getMessage());
        }
    }
    
    /**
     * Handle streaming requests - initiates SSE stream.
     */
    private static void handleStreamingRequest(Context ctx) {
        try {
            String body = ctx.body();
            ObjectNode request = (ObjectNode) mapper.readTree(body);
            
            // Validate JSON-RPC
            if (!request.has("jsonrpc") || !"2.0".equals(request.get("jsonrpc").asText())) {
                sendError(ctx, request.get("id"), -32600, "Invalid JSON-RPC request");
                return;
            }
            
            // Generate task ID for this stream
            String taskId = "task-" + System.currentTimeMillis() + "-" + 
                          Math.abs(request.hashCode());
            
            // Return stream URL
            ObjectNode response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.set("id", request.get("id"));
            
            ObjectNode result = mapper.createObjectNode();
            result.put("taskId", taskId);
            result.put("streamUrl", "http://localhost:" + PORT + "/stream/" + taskId);
            result.put("status", "streaming");
            response.set("result", result);
            
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(response));
            
            // Start streaming in background
            startStreaming(taskId, request);
            
        } catch (Exception e) {
            sendError(ctx, null, -32603, "Internal error: " + e.getMessage());
        }
    }
    
    /**
     * Start streaming content to connected client.
     */
    private static void startStreaming(String taskId, ObjectNode request) {
        new Thread(() -> {
            try {
                // Wait for client to connect
                Thread.sleep(100);
                
                SseEventEmitter emitter = activeStreams.get(taskId);
                if (emitter == null || emitter.isClosed()) {
                    System.out.println("[SSE] No client connected for task: " + taskId);
                    return;
                }
                
                // Extract skill and parameters
                ObjectNode params = (ObjectNode) request.get("params");
                String skill = params.has("skill") ? params.get("skill").asText() : "chat";
                
                System.out.println("[SSE] Starting stream for skill: " + skill);
                
                // Route to appropriate streaming handler
                switch (skill) {
                    case "chat" -> chatSkill.stream(params, emitter);
                    case "count" -> countSkill.stream(params, emitter);
                    case "story" -> storySkill.stream(params, emitter);
                    case "progress" -> progressSkill.stream(params, emitter);
                    default -> emitter.sendEvent("error", createStatusEvent("error", 
                        "Unknown skill: " + skill));
                }
                
                // Send completion
                emitter.sendEvent("complete", createStatusEvent("complete", "Stream finished"));
                
            } catch (Exception e) {
                System.err.println("[SSE] Streaming error: " + e.getMessage());
            } finally {
                activeStreams.remove(taskId);
                System.out.println("[SSE] Stream ended: " + taskId);
            }
        }).start();
    }
    
    /**
     * Process message synchronously.
     */
    private static ObjectNode processMessage(ObjectNode request) {
        ObjectNode response = mapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", request.get("id"));
        
        try {
            ObjectNode params = (ObjectNode) request.get("params");
            String skill = params.has("skill") ? params.get("skill").asText() : "chat";
            
            ObjectNode result = mapper.createObjectNode();
            result.put("skill", skill);
            result.put("status", "completed");
            result.put("message", "Use /stream endpoint for streaming responses");
            
            response.set("result", result);
        } catch (Exception e) {
            ObjectNode error = mapper.createObjectNode();
            error.put("code", -32603);
            error.put("message", e.getMessage());
            response.set("error", error);
        }
        
        return response;
    }
    
    private static ObjectNode createStatusEvent(String status, String message) {
        ObjectNode event = mapper.createObjectNode();
        event.put("status", status);
        event.put("message", message);
        event.put("timestamp", System.currentTimeMillis());
        return event;
    }
    
    /**
     * Send JSON-RPC error response.
     */
    private static void sendError(Context ctx, com.fasterxml.jackson.databind.JsonNode id, 
                                   int code, String message) {
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
    
    public static void removeStream(String taskId) {
        activeStreams.remove(taskId);
    }
}
