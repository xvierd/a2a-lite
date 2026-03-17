package com.example.auth.skills;

import com.example.auth.model.SecretResponse;
import com.example.auth.security.ApiKeyAuthenticator;
import com.example.auth.security.BearerTokenAuthenticator;
import com.example.auth.security.SecuritySchemes;

import java.util.Map;
import java.util.Set;

/**
 * GetSecretSkill - returns a secret message.
 * Requires authentication (any valid user).
 * Demonstrates basic authenticated skill.
 */
public class GetSecretSkill {
    
    private final ApiKeyAuthenticator apiKeyAuth;
    private final BearerTokenAuthenticator bearerAuth;
    
    public GetSecretSkill(ApiKeyAuthenticator apiKeyAuth, 
                          BearerTokenAuthenticator bearerAuth) {
        this.apiKeyAuth = apiKeyAuth;
        this.bearerAuth = bearerAuth;
    }
    
    /**
     * Skill metadata with security requirements.
     */
    public SkillMetadata getMetadata() {
        return new SkillMetadata(
            "get_secret",
            "Get Secret",
            "Returns a secret message for authenticated users",
            new SecuritySchemes.SecurityRequirement("apiKeyHeader"),
            new SecuritySchemes.SecurityRequirement("bearerAuth")
        );
    }
    
    /**
     * Execute the skill with authentication.
     */
    public SecretResponse execute(Map<String, String> headers, 
                                   Map<String, String> queryParams) {
        // Try API key authentication (header first, then query)
        String apiKey = headers.get("X-API-Key");
        if (apiKey == null) {
            apiKey = queryParams.get("api_key");
        }
        
        if (apiKey != null) {
            ApiKeyAuthenticator.AuthenticationResult result = apiKeyAuth.authenticate(apiKey);
            if (result.isSuccess()) {
                return new SecretResponse(
                    "The secret is: A2A is awesome!",
                    result.getUsername(),
                    String.join(", ", result.getRoles())
                );
            }
        }
        
        // Try Bearer token authentication
        String authHeader = headers.get("Authorization");
        if (authHeader != null) {
            BearerTokenAuthenticator.AuthenticationResult result = bearerAuth.authenticate(authHeader);
            if (result.isSuccess()) {
                return new SecretResponse(
                    "The secret is: A2A is awesome!",
                    result.getUsername(),
                    String.join(", ", result.getRoles())
                );
            }
        }
        
        // Authentication failed
        throw new SecurityException("Authentication required. Provide API key or Bearer token.");
    }
    
    /**
     * Skill metadata holder.
     */
    public static class SkillMetadata {
        private final String id;
        private final String name;
        private final String description;
        private final SecuritySchemes.SecurityRequirement[] securityRequirements;
        
        public SkillMetadata(String id, String name, String description,
                            SecuritySchemes.SecurityRequirement... securityRequirements) {
            this.id = id;
            this.name = name;
            this.description = description;
            this.securityRequirements = securityRequirements;
        }
        
        public String getId() { return id; }
        public String getName() { return name; }
        public String getDescription() { return description; }
        public SecuritySchemes.SecurityRequirement[] getSecurityRequirements() { 
            return securityRequirements; 
        }
    }
}
