package com.example.hello;

import io.javalin.Javalin;
import io.javalin.http.Context;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;

/**
 * Hello Agent - Google A2A SDK Implementation (Java)
 * 
 * This is the main entry point for the A2A agent. It sets up a Javalin
 * HTTP server and configures routes for A2A protocol communication.
 */
public class HelloAgent {
    
    private static final int PORT = 8787;
    private static final ObjectMapper mapper = new ObjectMapper();
    
    public static void main(String[] args) {
        System.out.println("=".repeat(60));
        System.out.println("Hello Agent - Google A2A SDK (Java)");
        System.out.println("=".repeat(60));
        
        // Create skill handler
        GreetingSkill greetingSkill = new GreetingSkill();
        MessageHandler messageHandler = new MessageHandler(greetingSkill);
        
        // Create agent card
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
            health.put("agent", "HelloAgent");
            ctx.json(health);
        });
        
        // Main A2A message endpoint
        app.post("/", ctx -> {
            handleMessage(ctx, messageHandler);
        });
        
        System.out.println("Agent: HelloAgent");
        System.out.println("Skills: greet");
        System.out.println("-".repeat(60));
        System.out.println("Starting server on http://localhost:" + PORT);
        System.out.println("Agent card: http://localhost:" + PORT + "/.well-known/agent.json");
        System.out.println("=".repeat(60));
        
        app.start(PORT);
    }
    
    /**
     * Create the agent card for A2A discovery.
     */
    private static ObjectNode createAgentCard() {
        ObjectNode card = mapper.createObjectNode();
        card.put("name", "HelloAgent");
        card.put("description", "A simple greeting agent using Google A2A SDK");
        card.put("version", "1.0.0");
        card.put("url", "http://localhost:" + PORT + "/");
        
        // Skills array
        ArrayNode skills = mapper.createArrayNode();
        
        // Greet skill
        ObjectNode greetSkill = mapper.createObjectNode();
        greetSkill.put("name", "greet");
        greetSkill.put("description", "Greet someone by name");
        
        ObjectNode inputSchema = mapper.createObjectNode();
        inputSchema.put("type", "object");
        ObjectNode properties = mapper.createObjectNode();
        ObjectNode nameProp = mapper.createObjectNode();
        nameProp.put("type", "string");
        nameProp.put("description", "Name of the person to greet");
        properties.set("name", nameProp);
        inputSchema.set("properties", properties);
        ArrayNode required = mapper.createArrayNode();
        required.add("name");
        inputSchema.set("required", required);
        greetSkill.set("inputSchema", inputSchema);
        
        ObjectNode outputSchema = mapper.createObjectNode();
        outputSchema.put("type", "string");
        greetSkill.set("outputSchema", outputSchema);
        
        skills.add(greetSkill);
        card.set("skills", skills);
        
        // Capabilities
        ObjectNode capabilities = mapper.createObjectNode();
        capabilities.put("streaming", false);
        capabilities.put("pushNotifications", false);
        card.set("capabilities", capabilities);
        
        return card;
    }
    
    /**
     * Handle incoming A2A messages.
     */
    private static void handleMessage(Context ctx, MessageHandler handler) {
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
            
            // Process message
            ObjectNode response = handler.handle(request);
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(response));
            
        } catch (Exception e) {
            sendError(ctx, null, -32603, "Internal error: " + e.getMessage());
        }
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
}
