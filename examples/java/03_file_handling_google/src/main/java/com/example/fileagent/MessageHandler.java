package com.example.fileagent;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.Map;

/**
 * Message Handler for File Agent
 * 
 * Handles A2A protocol message parsing, skill routing, file extraction,
 * and response formatting for file handling operations.
 */
public class MessageHandler {
    
    private final FileSkill fileSkill;
    private final ObjectMapper mapper;
    
    public MessageHandler(FileSkill fileSkill) {
        this.fileSkill = fileSkill;
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
            
            // Find text part containing skill call and file parts (v1.0 parts:
            // text is {"text": ...}, inline base64 file is {"raw", "mediaType", "filename"})
            String skillCallJson = null;
            ObjectNode filePart = null;

            for (int i = 0; i < parts.size(); i++) {
                ObjectNode part = (ObjectNode) parts.get(i);

                if (part.has("text")) {
                    skillCallJson = part.get("text").asText();
                } else if (part.has("raw")) {
                    filePart = part;
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
            Map<String, Object> result = executeSkill(skillName, skillParams, filePart);
            
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
     * Execute a skill by name with optional file data.
     */
    @SuppressWarnings("unchecked")
    private Map<String, Object> executeSkill(String skillName, ObjectNode params, ObjectNode filePart) {
        // Extract file data if present (v1.0 inline file part: raw/mediaType/filename)
        Map<String, Object> fileData = null;
        if (filePart != null && filePart.has("raw")) {
            fileData = Map.of(
                "name", filePart.has("filename") ? filePart.get("filename").asText() : "unknown",
                "mimeType", filePart.has("mediaType") ? filePart.get("mediaType").asText() : "text/plain",
                "data", filePart.get("raw").asText()
            );
        }
        
        // Extract inline file from params if present
        if (params.has("file") && fileData == null) {
            JsonNode inlineFile = params.get("file");
            if (inlineFile.isObject()) {
                ObjectNode fileObj = (ObjectNode) inlineFile;
                fileData = new java.util.HashMap<>();
                fileData.put("name", fileObj.has("name") ? fileObj.get("name").asText() : "unknown");
                fileData.put("mimeType", fileObj.has("mimeType") ? fileObj.get("mimeType").asText() : "text/plain");
                fileData.put("data", fileObj.has("data") ? fileObj.get("data").asText() : "");
            }
        }
        
        // Extract content from params
        String content = params.has("content") ? params.get("content").asText() : null;
        
        switch (skillName) {
            case "analyze":
                return fileSkill.analyze(content, fileData);
                
            case "convert_to_upper":
                return fileSkill.convertToUpper(content, fileData);
                
            case "generate_report":
                String title = params.has("title") ? params.get("title").asText() : "";
                String format = params.has("format") ? params.get("format").asText() : "json";
                Map<String, Object> reportData = new java.util.HashMap<>();
                if (params.has("data") && params.get("data").isObject()) {
                    ObjectNode dataObj = (ObjectNode) params.get("data");
                    dataObj.fields().forEachRemaining(entry -> {
                        JsonNode value = entry.getValue();
                        if (value.isTextual()) {
                            reportData.put(entry.getKey(), value.asText());
                        } else if (value.isNumber()) {
                            reportData.put(entry.getKey(), value.numberValue());
                        } else if (value.isBoolean()) {
                            reportData.put(entry.getKey(), value.asBoolean());
                        } else {
                            reportData.put(entry.getKey(), value.toString());
                        }
                    });
                }
                return fileSkill.generateReport(title, reportData, format);
                
            default:
                throw new IllegalArgumentException("Unknown skill: " + skillName);
        }
    }
    
    /**
     * Create a successful JSON-RPC response.
     */
    private ObjectNode createSuccessResponse(JsonNode id, Map<String, Object> result) {
        ObjectNode response = mapper.createObjectNode();
        response.put("jsonrpc", "2.0");
        response.set("id", id);
        
        ObjectNode resultObj = mapper.createObjectNode();
        ObjectNode messageObj = mapper.createObjectNode();
        messageObj.put("messageId", java.util.UUID.randomUUID().toString());
        messageObj.put("role", "ROLE_AGENT");

        ArrayNode parts = mapper.createArrayNode();

        // Add text part with result summary (v1.0: no type/kind field)
        ObjectNode textPart = mapper.createObjectNode();
        textPart.put("text", convertResultToJson(result));
        parts.add(textPart);

        // Add file part if report was generated with file (v1.0 inline base64 file part)
        if (result.containsKey("file") && result.get("file") instanceof Map) {
            @SuppressWarnings("unchecked")
            Map<String, Object> fileData = (Map<String, Object>) result.get("file");
            ObjectNode filePart = mapper.createObjectNode();
            filePart.put("raw", (String) fileData.get("data"));
            filePart.put("mediaType", (String) fileData.get("mimeType"));
            filePart.put("filename", (String) fileData.get("name"));
            parts.add(filePart);
        }
        
        messageObj.set("parts", parts);
        resultObj.set("message", messageObj);
        response.set("result", resultObj);
        
        return response;
    }
    
    /**
     * Create an error JSON-RPC response.
     */
    private ObjectNode createErrorResponse(JsonNode id, int code, String message) {
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
    
    /**
     * Convert result map to JSON string.
     */
    private String convertResultToJson(Map<String, Object> result) {
        StringBuilder sb = new StringBuilder();
        sb.append("{");
        boolean first = true;
        for (Map.Entry<String, Object> entry : result.entrySet()) {
            // Skip the file data in the text part (it's included separately)
            if ("file".equals(entry.getKey()) && entry.getValue() instanceof Map) {
                continue;
            }
            
            if (!first) sb.append(",");
            sb.append("\"").append(entry.getKey()).append("\":");
            Object value = entry.getValue();
            if (value instanceof String) {
                sb.append("\"").append(escapeJson((String) value)).append("\"");
            } else if (value instanceof Number) {
                sb.append(value);
            } else if (value instanceof Boolean) {
                sb.append(value);
            } else if (value instanceof Map) {
                sb.append("\"[object]\"");
            } else {
                sb.append("\"").append(escapeJson(value.toString())).append("\"");
            }
            first = false;
        }
        sb.append("}");
        return sb.toString();
    }
    
    private String escapeJson(String input) {
        return input.replace("\\", "\\\\")
                    .replace("\"", "\\\"")
                    .replace("\n", "\\n")
                    .replace("\r", "\\r")
                    .replace("\t", "\\t");
    }
}
