package com.example.streaming.skills;

import com.example.streaming.sse.SseEventEmitter;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

/**
 * Story Skill - Streaming Implementation
 * 
 * Demonstrates creative content generation with word-by-word streaming.
 */
public class StorySkill {
    
    private static final ObjectMapper mapper = new ObjectMapper();
    
    public void stream(ObjectNode params, SseEventEmitter emitter) {
        try {
            String theme = params.has("theme") ? 
                params.get("theme").asText() : "adventure";
            
            emitter.sendEvent("status", createStatus("generating", 
                "Creating a story about: " + theme));
            
            String story = generateStory(theme);
            String[] sentences = story.split("(?<=[.!?])\\s+");
            
            int wordIndex = 0;
            for (String sentence : sentences) {
                String[] words = sentence.split(" ");
                
                for (String word : words) {
                    word = word.trim();
                    if (!word.isEmpty()) {
                        emitter.sendToken(word + " ", wordIndex++, false);
                        Thread.sleep(80);
                    }
                }
                
                // Small pause between sentences
                Thread.sleep(300);
            }
            
            // Mark as complete
            emitter.sendToken("", wordIndex, true);
            emitter.sendEvent("status", createStatus("completed", "Story complete!"));
            
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            emitter.sendError("Story generation interrupted");
        } catch (Exception e) {
            emitter.sendError("Error: " + e.getMessage());
        }
    }
    
    private String generateStory(String theme) {
        String lower = theme.toLowerCase();
        
        if (lower.contains("space") || lower.contains("star")) {
            return "The starship drifted silently through the void. Captain Elena stared at the distant nebula, " +
                   "its colors dancing like cosmic flames. Suddenly, the sensors detected an anomaly. " +
                   "Something was out there, waiting in the darkness between stars.";
        } else if (lower.contains("magic") || lower.contains("fantasy")) {
            return "The ancient spellbook glowed with ethereal light. young wizard Kira traced the runes " +
                   "with trembling fingers, feeling power surge through her veins. The portal began to swirl, " +
                   "revealing a realm where dragons soared and magic was as common as breathing.";
        } else {
            return "Once upon a time in a land of streaming data, brave developers built agents that could " +
                   "speak in real-time. They crafted messages that flowed like rivers, connecting minds " +
                   "across the digital realm. And so the adventure of A2A streaming began.";
        }
    }
    
    private ObjectNode createStatus(String status, String message) {
        ObjectNode node = mapper.createObjectNode();
        node.put("status", status);
        node.put("message", message);
        return node;
    }
}
