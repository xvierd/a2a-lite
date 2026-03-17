package com.example.hello;

/**
 * Greeting Skill Implementation
 * 
 * This class contains the business logic for the greet skill.
 * It is separate from the HTTP handling and protocol concerns.
 */
public class GreetingSkill {
    
    /**
     * Greet someone by name.
     * 
     * @param name The name of the person to greet
     * @return A greeting message
     * @throws IllegalArgumentException if name is null or empty
     */
    public String greet(String name) {
        if (name == null || name.trim().isEmpty()) {
            throw new IllegalArgumentException("Name is required and cannot be empty");
        }
        return "Hello, " + name + "!";
    }
    
    /**
     * Get agent information.
     * 
     * @return Agent metadata
     */
    public AgentInfo getAgentInfo() {
        return new AgentInfo("HelloAgent", "1.0.0");
    }
    
    /**
     * Agent info record.
     */
    public record AgentInfo(String name, String version) {}
}
