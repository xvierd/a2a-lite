package com.example.auth;

import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import com.a2alite.auth.APIKeyAuth;

import java.util.Map;
import java.util.Set;

/**
 * Secure Agent - A2A Lite Example with Authentication (Java)
 * 
 * Demonstrates API Key authentication using the A2A Lite library.
 */
public class SecureAgent {
    
    public static void main(String[] args) {
        // Create API Key authentication provider
        // Keys are stored as hashes for security
        var auth = new APIKeyAuth(Set.of(
            "secret-key-user-12345",
            "secret-key-admin-67890"
        ), "X-API-Key");
        
        // Create agent with authentication
        var agent = Agent.builder()
            .name("SecureAgent")
            .description("A secure agent requiring API key authentication")
            .version("1.0.0")
            .auth(auth)
            .build();
        
        // Public skill (no special role required)
        agent.skill("status", SkillConfig.of("Get agent status"), params -> {
            return Map.of(
                "status", "operational",
                "agent", "SecureAgent",
                "version", "1.0.0",
                "authenticated", true
            );
        });
        
        // Protected skill - returns sensitive data
        agent.skill("get_secret", SkillConfig.of("Get a secret message"), params -> {
            return Map.of(
                "secret", "The secret is: A2A Lite is simpler!",
                "level", "confidential",
                "message", "This data requires authentication to access"
            );
        });
        
        // Admin skill
        agent.skill("admin_info", SkillConfig.of("Get administrative information"), params -> {
            return Map.of(
                "system", "A2A Lite Secure Server",
                "uptime", "99.9%",
                "admin_features", java.util.List.of("user_management", "logs", "config"),
                "message", "Admin access granted"
            );
        });
        
        System.out.println("Secure Agent with API Key authentication");
        System.out.println("Use header 'X-API-Key: secret-key-user-12345' to access");
        System.out.println();
        
        agent.run(8791);
    }
}
