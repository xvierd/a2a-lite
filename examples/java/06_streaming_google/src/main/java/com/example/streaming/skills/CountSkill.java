package com.example.streaming.skills;

import com.example.streaming.sse.StreamEmitter;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Count Skill - Streaming Implementation
 * 
 * Demonstrates progress-based streaming with numeric updates.
 */
public class CountSkill {
    
    public void stream(ObjectNode params, StreamEmitter emitter) {
        try {
            int to = params.has("to") ? params.get("to").asInt() : 10;
            to = Math.min(to, 100); // Cap at 100
            
            emitter.sendStatus("Starting count to " + to);
            
            for (int i = 1; i <= to; i++) {
                // Send progress update
                emitter.sendProgress(i, to, "Counting: " + i);
                
                // Send the number as an artifact chunk
                emitter.sendText(i + " ");
                
                // Small delay between numbers
                Thread.sleep(200);
            }
            
            emitter.complete("Finished counting to " + to);
            
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            emitter.sendError("Counting interrupted");
        } catch (Exception e) {
            emitter.sendError("Error: " + e.getMessage());
        }
    }
}
