package com.example.hello;

import com.a2alite.Agent;
import com.a2alite.SkillConfig;

import java.util.Map;

/**
 * Hello Agent - A2A Lite Example (Java)
 * 
 * A simple greeting agent using the real A2A Lite library.
 * 
 * <pre>{@code
 *   Agent.builder()
 *       .name("HelloAgent")
 *       .description("A simple greeting agent")
 *       .build()
 *       .skill("greet", params -> "Hello, " + params.get("name") + "!")
 *       .run();
 * }</pre>
 */
public class HelloAgent {
    
    public static void main(String[] args) {
        // Create agent using the builder pattern
        var agent = Agent.builder()
            .name("HelloAgent")
            .description("A simple greeting agent using A2A Lite")
            .version("1.0.0")
            .build();
        
        // Register skills using lambda handlers
        // params is Map<String, Object>
        agent.skill("greet", SkillConfig.of("Greet someone by name"), params -> {
            String name = (String) params.getOrDefault("name", "World");
            return Map.of("message", "Hello, " + name + "!");
        });
        
        agent.skill("info", SkillConfig.of("Get agent information"), params -> {
            return Map.of(
                "name", "HelloAgent",
                "version", "1.0.0",
                "status", "operational",
                "features", java.util.List.of("greeting", "info")
            );
        });
        
        // Start the server on port 8787
        agent.run(8787);
    }
}
