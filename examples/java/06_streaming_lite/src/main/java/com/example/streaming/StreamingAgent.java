package com.example.streaming;

import com.a2alite.Agent;
import com.a2alite.SkillConfig;

import java.util.Map;

/**
 * Streaming Agent - A2A Lite Example (Java)
 * 
 * Note: This example demonstrates regular skills with simulated streaming.
 * For full streaming support with the official A2A SDK, use SkillConfig.withStreaming()
 * which enables streaming capabilities in the agent card.
 */
public class StreamingAgent {
    
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("StreamingAgent")
            .description("Agent with simulated streaming capabilities")
            .version("1.0.0")
            .build();
        
        // Chat skill - returns a response
        agent.skill("chat", SkillConfig.of("Chat with the agent"), params -> {
            String message = (String) params.getOrDefault("message", "Hello");
            String response = generateResponse(message);
            
            return Map.of(
                "message", message,
                "response", response,
                "streaming_supported", true,
                "note", "For real streaming, use the A2A SDK with streaming flag enabled"
            );
        });
        
        // Count skill
        agent.skill("count", SkillConfig.of("Count to a number"), params -> {
            int to = ((Number) params.getOrDefault("to", 10)).intValue();
            to = Math.min(to, 100);
            
            var numbers = new java.util.ArrayList<Integer>();
            for (int i = 1; i <= to; i++) {
                numbers.add(i);
            }
            
            return Map.of(
                "counted_to", to,
                "numbers", numbers,
                "message", "Counted from 1 to " + to
            );
        });
        
        // Progress skill
        agent.skill("progress", SkillConfig.of("Simulate progress steps"), params -> {
            int steps = ((Number) params.getOrDefault("steps", 5)).intValue();
            steps = Math.min(steps, 20);
            
            var progressList = new java.util.ArrayList<Map<String, Object>>();
            for (int i = 1; i <= steps; i++) {
                progressList.add(Map.of(
                    "step", i,
                    "total", steps,
                    "message", "Processing step " + i + " of " + steps,
                    "percent", (int) ((i * 100.0) / steps)
                ));
            }
            
            return Map.of(
                "steps_completed", steps,
                "progress", progressList,
                "status", "complete"
            );
        });
        
        // For true streaming, mark the skill with streaming config:
        // agent.skill("stream_chat", SkillConfig.withStreaming(), params -> { ... });
        // This enables streaming=true in the agent card capabilities
        
        System.out.println("Streaming Agent (A2A Lite)");
        System.out.println("Note: True streaming requires the A2A SDK server implementation");
        System.out.println("This example demonstrates the simplified A2A Lite API");
        System.out.println();
        
        agent.run(8792);
    }
    
    private static String generateResponse(String message) {
        String lower = message.toLowerCase();
        if (lower.contains("hello")) {
            return "Hello! Welcome to A2A Lite. This is much simpler than the Google SDK!";
        } else if (lower.contains("help")) {
            return "I support chat, counting, and progress tracking. Use the A2A protocol to interact with me.";
        }
        return "You said: " + message + ". A2A Lite makes agent development effortless.";
    }
}
