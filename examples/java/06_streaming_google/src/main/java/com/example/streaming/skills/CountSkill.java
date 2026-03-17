package com.example.streaming.skills;

import com.example.streaming.sse.SseEventEmitter;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Count Skill - Streaming Implementation
 * 
 * Demonstrates progress-based streaming with numeric updates.
 */
public class CountSkill {
    
    private static final ObjectMapper mapper = new ObjectMapper();
    
    public void stream(ObjectNode params, SseEventEmitter emitter) {
        try {
            int to = params.has("to") ? params.get("to").asInt() : 10;
            to = Math.min(to, 100); // Cap at 100
            
            emitter.sendEvent("status", createStatus("started", "Starting count to " + to));
            
            for (int i = 1; i <= to; i++) {
                // Send progress update
                emitter.sendProgress(i, to, "Counting: " + i);
                
                // Send the number as a chunk
                emitter.sendChunk(String.valueOf(i));
                
                // Small delay between numbers
                Thread.sleep(200);
            }
            
            emitter.sendEvent("status", createStatus("completed", "Finished counting to " + to));
            
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            emitter.sendError("Counting interrupted");
        } catch (Exception e) {
            emitter.sendError("Error: " + e.getMessage());
        }
    }
    
    private ObjectNode createStatus(String status, String message) {
        ObjectNode node = mapper.createObjectNode();
        node.put("status", status);
        node.put("message", message);
        return node;
    }
}
