package com.example.streaming.skills;

import com.example.streaming.sse.StreamEmitter;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Chat Skill - Streaming Implementation
 * 
 * Demonstrates streaming chat responses word by word.
 */
public class ChatSkill {
    
    public void stream(ObjectNode params, StreamEmitter emitter) {
        try {
            String message = params.has("message") ? 
                params.get("message").asText() : "Hello";
            
            // Simulate processing time
            emitter.sendStatus("Analyzing message...");
            Thread.sleep(500);
            
            // Generate response
            String response = generateResponse(message);
            String[] words = response.split(" ");
            
            // Stream word by word
            StringBuilder built = new StringBuilder();
            for (String word : words) {
                built.append(word).append(" ");
                
                emitter.sendText(word + " ");
                
                // Simulate typing delay
                Thread.sleep(100);
            }
            
            emitter.complete(built.toString().trim());
            
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            emitter.sendError("Streaming interrupted");
        } catch (Exception e) {
            emitter.sendError("Error: " + e.getMessage());
        }
    }
    
    private String generateResponse(String message) {
        String lower = message.toLowerCase();
        
        if (lower.contains("hello") || lower.contains("hi")) {
            return "Hello! Welcome to the streaming chat demo. I'm sending this message word by word to demonstrate Server-Sent Events in action.";
        } else if (lower.contains("help")) {
            return "I can help you with: general chat, counting, story generation, and progress tracking. Each skill demonstrates different streaming patterns.";
        } else if (lower.contains("stream")) {
            return "Streaming allows real-time delivery of content. Instead of waiting for the entire response, you receive data as it becomes available.";
        } else {
            return "You said: " + message + ". This is a streaming response where each word arrives progressively through the SSE connection.";
        }
    }
}
