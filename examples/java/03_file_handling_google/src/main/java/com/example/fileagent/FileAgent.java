package com.example.fileagent;

import io.javalin.Javalin;
import io.javalin.http.Context;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;

/**
 * File Agent - Google A2A SDK Implementation (Java)
 * 
 * Multi-skill file handling agent demonstrating the official A2A SDK approach.
 * Supports file upload, text analysis, case conversion, and report generation.
 */
public class FileAgent {
    
    private static final int PORT = 8789;
    private static final ObjectMapper mapper = new ObjectMapper();
    
    public static void main(String[] args) {
        System.out.println("=".repeat(70));
        System.out.println("File Agent - Google A2A SDK (Java)");
        System.out.println("=".repeat(70));
        
        // Create skill handler
        FileSkill fileSkill = new FileSkill();
        MessageHandler messageHandler = new MessageHandler(fileSkill);
        
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
            health.put("agent", "FileAgent");
            health.put("version", "1.0.0");
            ctx.json(health);
        });
        
        // Main A2A message endpoint
        app.post("/", ctx -> {
            handleMessage(ctx, messageHandler);
        });
        
        System.out.println("Agent: FileAgent");
        System.out.println("Skills: analyze, convert_to_upper, generate_report");
        System.out.println("File Support: upload, text/plain, application/json");
        System.out.println("-".repeat(70));
        System.out.println("Starting server on http://localhost:" + PORT);
        System.out.println("Agent card: http://localhost:" + PORT + "/.well-known/agent.json");
        System.out.println("=".repeat(70));
        
        app.start(PORT);
    }
    
    /**
     * Create the agent card for A2A discovery with file capabilities.
     */
    private static ObjectNode createAgentCard() {
        ObjectNode card = mapper.createObjectNode();
        card.put("name", "FileAgent");
        card.put("description", "A file handling agent with text analysis and conversion capabilities");
        card.put("version", "1.0.0");
        card.put("url", "http://localhost:" + PORT + "/");
        
        // Capabilities with file support
        ObjectNode capabilities = mapper.createObjectNode();
        capabilities.put("streaming", false);
        capabilities.put("pushNotifications", false);
        
        // File handling capabilities
        ObjectNode fileCapabilities = mapper.createObjectNode();
        fileCapabilities.put("enabled", true);
        fileCapabilities.put("maxSize", 10485760); // 10MB
        ArrayNode acceptedMimeTypes = mapper.createArrayNode();
        acceptedMimeTypes.add("text/plain");
        acceptedMimeTypes.add("text/markdown");
        acceptedMimeTypes.add("application/json");
        acceptedMimeTypes.add("text/csv");
        fileCapabilities.set("acceptedMimeTypes", acceptedMimeTypes);
        capabilities.set("fileHandling", fileCapabilities);
        
        card.set("capabilities", capabilities);
        
        // Skills array
        ArrayNode skills = mapper.createArrayNode();
        
        // analyze skill
        skills.add(createSkill("analyze", 
            "Analyze text content and return statistics (word count, line count, char count)",
            createAnalyzeSchema()));
        
        // convert_to_upper skill
        skills.add(createSkill("convert_to_upper",
            "Convert text content to uppercase",
            createConvertSchema()));
        
        // generate_report skill
        skills.add(createSkill("generate_report",
            "Generate a formatted report from provided data",
            createReportSchema()));
        
        card.set("skills", skills);
        
        return card;
    }
    
    private static ObjectNode createSkill(String name, String description, ObjectNode inputSchema) {
        ObjectNode skill = mapper.createObjectNode();
        skill.put("name", name);
        skill.put("description", description);
        skill.set("inputSchema", inputSchema);
        return skill;
    }
    
    private static ObjectNode createAnalyzeSchema() {
        ObjectNode schema = mapper.createObjectNode();
        schema.put("type", "object");
        
        ObjectNode properties = mapper.createObjectNode();
        
        // content parameter
        ObjectNode contentProp = mapper.createObjectNode();
        contentProp.put("type", "string");
        contentProp.put("description", "Text content to analyze");
        properties.set("content", contentProp);
        
        // file parameter
        ObjectNode fileProp = mapper.createObjectNode();
        fileProp.put("type", "object");
        fileProp.put("description", "File object with name, mimeType, and base64 data");
        ObjectNode fileProps = mapper.createObjectNode();
        fileProps.set("name", mapper.createObjectNode().put("type", "string"));
        fileProps.set("mimeType", mapper.createObjectNode().put("type", "string"));
        fileProps.set("data", mapper.createObjectNode().put("type", "string"));
        fileProp.set("properties", fileProps);
        properties.set("file", fileProp);
        
        schema.set("properties", properties);
        return schema;
    }
    
    private static ObjectNode createConvertSchema() {
        ObjectNode schema = mapper.createObjectNode();
        schema.put("type", "object");
        
        ObjectNode properties = mapper.createObjectNode();
        
        // content parameter
        ObjectNode contentProp = mapper.createObjectNode();
        contentProp.put("type", "string");
        contentProp.put("description", "Text content to convert");
        properties.set("content", contentProp);
        
        // file parameter
        ObjectNode fileProp = mapper.createObjectNode();
        fileProp.put("type", "object");
        fileProp.put("description", "File object to convert");
        properties.set("file", fileProp);
        
        schema.set("properties", properties);
        return schema;
    }
    
    private static ObjectNode createReportSchema() {
        ObjectNode schema = mapper.createObjectNode();
        schema.put("type", "object");
        
        ObjectNode properties = mapper.createObjectNode();
        
        // title parameter
        ObjectNode titleProp = mapper.createObjectNode();
        titleProp.put("type", "string");
        titleProp.put("description", "Report title");
        properties.set("title", titleProp);
        
        // data parameter
        ObjectNode dataProp = mapper.createObjectNode();
        dataProp.put("type", "object");
        dataProp.put("description", "Report data as key-value pairs");
        properties.set("data", dataProp);
        
        // format parameter
        ObjectNode formatProp = mapper.createObjectNode();
        formatProp.put("type", "string");
        formatProp.put("description", "Output format (json, markdown, text)");
        formatProp.put("enum", mapper.createArrayNode().add("json").add("markdown").add("text"));
        properties.set("format", formatProp);
        
        schema.set("properties", properties);
        
        ArrayNode required = mapper.createArrayNode();
        required.add("title");
        required.add("data");
        schema.set("required", required);
        
        return schema;
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
