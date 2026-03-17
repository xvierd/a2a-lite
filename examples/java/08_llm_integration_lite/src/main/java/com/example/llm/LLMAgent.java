package com.example.llm;

import com.a2alite.Agent;
import com.a2alite.SkillConfig;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

/**
 * LLM Agent - A2A Lite Example (Java)
 * 
 * LLM-powered agent with conversation memory and tool calling.
 */
public class LLMAgent {
    
    // Simple conversation memory (session_id -> list of messages)
    private static final Map<String, List<Map<String, String>>> sessions = new HashMap<>();
    
    public static void main(String[] args) {
        String provider = System.getenv().getOrDefault("LLM_PROVIDER", "openai");
        String model = System.getenv("LLM_MODEL");
        boolean llmReady = System.getenv("OPENAI_API_KEY") != null || 
                          System.getenv("ANTHROPIC_API_KEY") != null;
        
        String actualModel = model != null ? model : 
            (provider.equals("anthropic") ? "claude-3-sonnet" : "gpt-4o-mini");
        
        var agent = Agent.builder()
            .name("LLMAgent")
            .description("AI assistant with memory and tools using A2A Lite")
            .version("1.0.0")
            .build();
        
        // Chat skill with memory
        agent.skill("chat", SkillConfig.of("Chat with AI assistant"), params -> {
            String message = (String) params.getOrDefault("message", "");
            String sessionId = (String) params.getOrDefault("session_id", "default");
            
            if (!llmReady) {
                return Map.of(
                    "error", "LLM not configured",
                    "message", "Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variable"
                );
            }
            
            if (message.isEmpty()) {
                return Map.of("error", "No message provided");
            }
            
            // Get or create session
            List<Map<String, String>> history = sessions.computeIfAbsent(
                sessionId, k -> new ArrayList<>()
            );
            
            // Add system message if first interaction
            if (history.isEmpty()) {
                history.add(Map.of(
                    "role", "system",
                    "content", "You are a helpful AI assistant. You can use tools: calculator, get_current_time."
                ));
            }
            
            // Check for tool calls in message
            String response = processWithTools(message);
            
            // Add to history
            history.add(Map.of("role", "user", "content", message));
            history.add(Map.of("role", "assistant", "content", response));
            
            // Trim history if too long
            if (history.size() > 12) {
                List<Map<String, String>> trimmed = new ArrayList<>();
                trimmed.add(history.get(0)); // Keep system
                trimmed.addAll(history.subList(history.size() - 10, history.size()));
                sessions.put(sessionId, trimmed);
            }
            
            return Map.of(
                "response", response,
                "session_id", sessionId,
                "history_length", history.size(),
                "tools_used", detectTools(message)
            );
        });
        
        // Clear memory skill
        agent.skill("clear_memory", SkillConfig.of("Clear conversation memory"), params -> {
            String sessionId = (String) params.getOrDefault("session_id", "default");
            sessions.remove(sessionId);
            return Map.of(
                "message", "Memory cleared",
                "session_id", sessionId
            );
        });
        
        // Info skill
        agent.skill("info", SkillConfig.of("Get agent information"), params -> {
            return Map.of(
                "name", "LLMAgent",
                "description", "AI assistant with LLM support",
                "version", "1.0.0",
                "llm_provider", provider,
                "llm_model", actualModel,
                "llm_ready", llmReady,
                "skills", java.util.List.of("chat", "clear_memory", "info"),
                "features", java.util.List.of("memory", "tool_calling", "multi_turn")
            );
        });
        
        System.out.println("LLM Agent (A2A Lite)");
        System.out.println("Provider: " + provider);
        System.out.println("Model: " + actualModel);
        System.out.println("LLM Ready: " + llmReady);
        System.out.println();
        
        agent.run(8794);
    }
    
    private static String processWithTools(String message) {
        String lower = message.toLowerCase();
        
        // Calculator tool
        if (lower.matches(".*\\b(calculate|what is|compute|math)\\b.*")) {
            try {
                String expr = extractExpression(message);
                double result = evaluateExpression(expr);
                return "I'll calculate that for you.\n\n" + expr + " = " + result;
            } catch (Exception e) {
                // Fall through to default
            }
        }
        
        // Time tool
        if (lower.matches(".*\\b(time|clock|hour|date)\\b.*")) {
            LocalDateTime now = LocalDateTime.now();
            String time = now.format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss"));
            return "The current time is: " + time;
        }
        
        // Weather tool (simulated)
        if (lower.matches(".*\\b(weather|temperature)\\b.*")) {
            String location = extractLocation(message);
            String[] conditions = {"sunny", "cloudy", "rainy", "partly cloudy"};
            int temp = 15 + (int) (Math.random() * 15);
            String condition = conditions[(int) (Math.random() * conditions.length)];
            return String.format("Current weather in %s: %s, %d°C (simulated)", location, condition, temp);
        }
        
        // Default response (simulated LLM)
        return "This is a simulated LLM response. In production with API keys, this would call " +
               "the actual " + System.getenv().getOrDefault("LLM_PROVIDER", "OpenAI") + " API.\n\n" +
               "You asked about: " + message;
    }
    
    private static List<String> detectTools(String message) {
        String lower = message.toLowerCase();
        var tools = new ArrayList<String>();
        if (lower.matches(".*\\b(calculate|what is|compute|math)\\b.*")) tools.add("calculator");
        if (lower.matches(".*\\b(time|clock|hour|date)\\b.*")) tools.add("get_current_time");
        if (lower.matches(".*\\b(weather|temperature)\\b.*")) tools.add("get_weather");
        return tools;
    }
    
    private static String extractExpression(String message) {
        return message.replaceAll("[^0-9+\\-*/().\\s]", "").trim();
    }
    
    private static String extractLocation(String message) {
        String[] parts = message.toLowerCase().split("\\bin\\b");
        if (parts.length > 1) {
            return parts[1].trim().split("\\s+")[0].replaceAll("[^a-z]", "");
        }
        return "your location";
    }
    
    private static double evaluateExpression(String expr) {
        expr = expr.replaceAll("\\s+", "");
        
        try {
            return Double.parseDouble(expr);
        } catch (NumberFormatException e) {
            // Simple addition/subtraction
            for (int i = expr.length() - 1; i >= 0; i--) {
                char c = expr.charAt(i);
                if (c == '+' || c == '-') {
                    double left = evaluateExpression(expr.substring(0, i));
                    double right = evaluateExpression(expr.substring(i + 1));
                    return c == '+' ? left + right : left - right;
                }
            }
            // Multiplication/division
            for (int i = expr.length() - 1; i >= 0; i--) {
                char c = expr.charAt(i);
                if (c == '*' || c == '/') {
                    double left = evaluateExpression(expr.substring(0, i));
                    double right = evaluateExpression(expr.substring(i + 1));
                    return c == '*' ? left * right : left / right;
                }
            }
        }
        throw new IllegalArgumentException("Could not evaluate: " + expr);
    }
}
