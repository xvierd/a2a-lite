package com.example.calculator;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.Map;

/**
 * Message Handler for Calculator Agent
 */
public class MessageHandler {
    
    private final CalculatorSkill calculator;
    private final ObjectMapper mapper;
    
    public MessageHandler(CalculatorSkill calculator) {
        this.calculator = calculator;
        this.mapper = new ObjectMapper();
    }
    
    public ObjectNode handle(ObjectNode request) {
        try {
            ObjectNode params = (ObjectNode) request.get("params");
            ObjectNode message = (ObjectNode) params.get("message");
            ArrayNode parts = (ArrayNode) message.get("parts");
            
            String skillCallJson = null;
            for (int i = 0; i < parts.size(); i++) {
                ObjectNode part = (ObjectNode) parts.get(i);
                if ("text".equals(part.get("type").asText())) {
                    skillCallJson = part.get("text").asText();
                    break;
                }
            }
            
            if (skillCallJson == null) {
                return createError(request.get("id"), -32602, "No skill call");
            }
            
            ObjectNode skillCall = (ObjectNode) mapper.readTree(skillCallJson);
            String skillName = skillCall.get("skill").asText();
            ObjectNode skillParams = (ObjectNode) skillCall.get("params");
            
            Map<String, Object> result = executeSkill(skillName, skillParams);
            return createSuccess(request.get("id"), result);
            
        } catch (IllegalArgumentException e) {
            return createError(request.get("id"), -32000, e.getMessage());
        } catch (Exception e) {
            return createError(request.get("id"), -32603, e.getMessage());
        }
    }
    
    private Map<String, Object> executeSkill(String name, ObjectNode params) {
        double a = params.has("a") ? params.get("a").asDouble() : 0;
        double b = params.has("b") ? params.get("b").asDouble() : 0;
        
        return switch (name) {
            case "add" -> calculator.add(a, b);
            case "subtract" -> calculator.subtract(a, b);
            case "multiply" -> calculator.multiply(a, b);
            case "divide" -> calculator.divide(a, b);
            case "power" -> {
                double base = params.get("base").asDouble();
                double exp = params.get("exponent").asDouble();
                yield calculator.power(base, exp);
            }
            default -> throw new IllegalArgumentException("Unknown skill: " + name);
        };
    }
    
    private ObjectNode createSuccess(JsonNode id, Map<String, Object> result) {
        ObjectNode response = mapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", id);
        
        ObjectNode resultObj = mapper.createObjectNode();
        ObjectNode messageObj = mapper.createObjectNode();
        messageObj.put("role", "agent");
        
        ArrayNode parts = mapper.createArrayNode();
        ObjectNode textPart = mapper.createObjectNode();
        textPart.put("type", "text");
        
        // Convert result map to JSON string
        StringBuilder sb = new StringBuilder("{");
        boolean first = true;
        for (Map.Entry<String, Object> entry : result.entrySet()) {
            if (!first) sb.append(",");
            sb.append("\"").append(entry.getKey()).append("\":");
            sb.append(entry.getValue());
            first = false;
        }
        sb.append("}");
        
        textPart.put("text", sb.toString());
        parts.add(textPart);
        messageObj.set("parts", parts);
        resultObj.set("message", messageObj);
        response.set("result", resultObj);
        
        return response;
    }
    
    private ObjectNode createError(JsonNode id, int code, String message) {
        ObjectNode response = mapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", id);
        ObjectNode error = mapper.createObjectNode();
        error.put("code", code);
        error.put("message", message);
        response.set("error", error);
        return response;
    }
}
