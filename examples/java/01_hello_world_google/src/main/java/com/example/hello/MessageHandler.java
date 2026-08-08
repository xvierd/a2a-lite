package com.example.hello;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;

/**
 * Message Handler
 * 
 * Handles A2A protocol message parsing, skill routing, and response formatting.
 * This class bridges the HTTP layer with the business logic layer.
 */
public class MessageHandler {
    
    private final GreetingSkill greetingSkill;
    private final ObjectMapper mapper;
    
    public MessageHandler(GreetingSkill greetingSkill) {
        this.greetingSkill = greetingSkill;
        this.mapper = new ObjectMapper();
    }
    
    /**
     * Handle an A2A JSON-RPC message.
     * 
     * @param request The JSON-RPC request
     * @return The JSON-RPC response
     */
    public ObjectNode handle(ObjectNode request) {
        try {
            // Extract skill call from message
            ObjectNode params = (ObjectNode) request.get("params");
            ObjectNode message = (ObjectNode) params.get("message");
            ArrayNode parts = (ArrayNode) message.get("parts");

            // Find text part containing skill call (v1.0 parts: {"text": ...})
            String skillCallJson = null;
            for (int i = 0; i < parts.size(); i++) {
                ObjectNode part = (ObjectNode) parts.get(i);
                if (part.has("text")) {
                    skillCallJson = part.get("text").asText();
                    break;
                }
            }
            
            if (skillCallJson == null) {
                return createErrorResponse(request.get("id"), -32602, "No skill call found");
            }
            
            // Parse skill call
            ObjectNode skillCall = (ObjectNode) mapper.readTree(skillCallJson);
            String skillName = skillCall.has("skill") ? skillCall.get("skill").asText() : "";
            ObjectNode skillParams = skillCall.has("params") ? 
                (ObjectNode) skillCall.get("params") : mapper.createObjectNode();
            
            // Execute skill
            Object result = executeSkill(skillName, skillParams);
            
            // Create success response
            return createSuccessResponse(request.get("id"), result);
            
        } catch (IllegalArgumentException e) {
            return createErrorResponse(request.get("id"), -32000, e.getMessage());
        } catch (Exception e) {
            return createErrorResponse(request.get("id"), -32603, 
                "Internal error: " + e.getMessage());
        }
    }
    
    /**
     * Execute a skill by name.
     */
    private Object executeSkill(String skillName, ObjectNode params) {
        if ("greet".equals(skillName)) {
            String name = params.has("name") ? params.get("name").asText() : "";
            return greetingSkill.greet(name);
        }
        
        throw new IllegalArgumentException("Unknown skill: " + skillName);
    }
    
    /**
     * Create a successful JSON-RPC response.
     */
    private ObjectNode createSuccessResponse(com.fasterxml.jackson.databind.JsonNode id, 
                                             Object result) {
        ObjectNode response = mapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", id);
        
        ObjectNode resultObj = mapper.createObjectNode();
        ObjectNode messageObj = mapper.createObjectNode();
        messageObj.put("messageId", java.util.UUID.randomUUID().toString());
        messageObj.put("role", "ROLE_AGENT");

        ArrayNode parts = mapper.createArrayNode();
        ObjectNode textPart = mapper.createObjectNode();
        textPart.put("text", result.toString());
        parts.add(textPart);
        messageObj.set("parts", parts);
        
        resultObj.set("message", messageObj);
        response.set("result", resultObj);
        
        return response;
    }
    
    /**
     * Create an error JSON-RPC response.
     */
    private ObjectNode createErrorResponse(com.fasterxml.jackson.databind.JsonNode id, 
                                           int code, String message) {
        ObjectNode response = mapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        if (id != null) {
            response.set("id", id);
        } else {
            response.putNull("id");
        }
        
        ObjectNode errorObj = mapper.createObjectNode();
        errorObj.put("code", code);
        errorObj.put("message", message);
        response.set("error", errorObj);
        
        return response;
    }
}
