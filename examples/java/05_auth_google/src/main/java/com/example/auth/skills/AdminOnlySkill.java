package com.example.auth.skills;

import com.example.auth.model.AdminResponse;
import com.example.auth.security.ApiKeyAuthenticator;
import com.example.auth.security.BearerTokenAuthenticator;
import com.example.auth.security.SecuritySchemes;

import java.util.Map;
import java.util.Set;

/**
 * AdminOnlySkill - administrative operations.
 * Requires ADMIN role only.
 * Demonstrates strict role-based access control.
 */
public class AdminOnlySkill {
    
    private final ApiKeyAuthenticator apiKeyAuth;
    private final BearerTokenAuthenticator bearerAuth;
    
    public AdminOnlySkill(ApiKeyAuthenticator apiKeyAuth, 
                          BearerTokenAuthenticator bearerAuth) {
        this.apiKeyAuth = apiKeyAuth;
        this.bearerAuth = bearerAuth;
    }
    
    /**
     * Skill metadata with security requirements.
     */
    public GetSecretSkill.SkillMetadata getMetadata() {
        return new GetSecretSkill.SkillMetadata(
            "admin_only",
            "Admin Only",
            "Administrative operations - requires ADMIN role",
            new SecuritySchemes.SecurityRequirement("apiKeyHeader", "ADMIN"),
            new SecuritySchemes.SecurityRequirement("bearerAuth", "ADMIN")
        );
    }
    
    /**
     * Execute the skill with strict ADMIN role check.
     */
    public AdminResponse execute(Map<String, String> headers, 
                                  Map<String, String> queryParams,
                                  String operation) {
        // Try API key authentication
        String apiKey = headers.get("X-API-Key");
        if (apiKey == null) {
            apiKey = queryParams.get("api_key");
        }
        
        if (apiKey != null) {
            ApiKeyAuthenticator.AuthenticationResult result = apiKeyAuth.authenticate(apiKey);
            if (result.isSuccess()) {
                // Strict ADMIN check
                Set<String> roles = result.getRoles();
                if (roles.contains("ADMIN")) {
                    return performAdminOperation(operation, result.getUsername());
                } else {
                    throw new SecurityException(
                        "Admin access required. Your roles: " + String.join(", ", roles));
                }
            }
        }
        
        // Try Bearer token authentication
        String authHeader = headers.get("Authorization");
        if (authHeader != null) {
            BearerTokenAuthenticator.AuthenticationResult result = bearerAuth.authenticate(authHeader);
            if (result.isSuccess()) {
                // Strict ADMIN check
                Set<String> roles = result.getRoles();
                if (roles.contains("ADMIN")) {
                    return performAdminOperation(operation, result.getUsername());
                } else {
                    throw new SecurityException(
                        "Admin access required. Your roles: " + String.join(", ", roles));
                }
            }
        }
        
        throw new SecurityException("Admin authentication required.");
    }
    
    private AdminResponse performAdminOperation(String operation, String adminName) {
        String op = operation != null ? operation : "status";
        String message;
        
        switch (op) {
            case "status":
                message = "System status: All services operational";
                break;
            case "reload":
                message = "Configuration reloaded successfully";
                break;
            case "clear-cache":
                message = "Cache cleared successfully";
                break;
            default:
                message = "Unknown operation: " + op;
        }
        
        return new AdminResponse(message, op, adminName);
    }
}
