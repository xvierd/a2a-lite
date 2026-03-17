package com.example.auth.skills;

import com.example.auth.model.UserInfo;
import com.example.auth.security.ApiKeyAuthenticator;
import com.example.auth.security.BearerTokenAuthenticator;
import com.example.auth.security.SecuritySchemes;

import java.util.Arrays;
import java.util.Map;
import java.util.Set;

/**
 * GetUserInfoSkill - returns user information.
 * Requires USER or ADMIN role.
 * Demonstrates role-based access control.
 */
public class GetUserInfoSkill {
    
    private final ApiKeyAuthenticator apiKeyAuth;
    private final BearerTokenAuthenticator bearerAuth;
    
    public GetUserInfoSkill(ApiKeyAuthenticator apiKeyAuth, 
                            BearerTokenAuthenticator bearerAuth) {
        this.apiKeyAuth = apiKeyAuth;
        this.bearerAuth = bearerAuth;
    }
    
    /**
     * Skill metadata with security requirements.
     */
    public GetSecretSkill.SkillMetadata getMetadata() {
        return new GetSecretSkill.SkillMetadata(
            "get_user_info",
            "Get User Info",
            "Returns detailed user information for authenticated users",
            new SecuritySchemes.SecurityRequirement("apiKeyHeader", "USER", "ADMIN"),
            new SecuritySchemes.SecurityRequirement("bearerAuth", "USER", "ADMIN")
        );
    }
    
    /**
     * Execute the skill with role-based authorization.
     */
    public UserInfo execute(Map<String, String> headers, 
                            Map<String, String> queryParams) {
        // Try API key authentication
        String apiKey = headers.get("X-API-Key");
        if (apiKey == null) {
            apiKey = queryParams.get("api_key");
        }
        
        if (apiKey != null) {
            ApiKeyAuthenticator.AuthenticationResult result = apiKeyAuth.authenticate(apiKey);
            if (result.isSuccess()) {
                // Check role authorization
                Set<String> roles = result.getRoles();
                if (roles.contains("USER") || roles.contains("ADMIN")) {
                    return createUserInfo(result.getUsername(), roles);
                } else {
                    throw new SecurityException(
                        "Insufficient permissions. Required: USER or ADMIN");
                }
            }
        }
        
        // Try Bearer token authentication
        String authHeader = headers.get("Authorization");
        if (authHeader != null) {
            BearerTokenAuthenticator.AuthenticationResult result = bearerAuth.authenticate(authHeader);
            if (result.isSuccess()) {
                // Check role authorization
                Set<String> roles = result.getRoles();
                if (roles.contains("USER") || roles.contains("ADMIN")) {
                    return createUserInfo(result.getUsername(), roles);
                } else {
                    throw new SecurityException(
                        "Insufficient permissions. Required: USER or ADMIN");
                }
            }
        }
        
        throw new SecurityException("Authentication required.");
    }
    
    private UserInfo createUserInfo(String username, Set<String> roles) {
        return new UserInfo(
            "usr_" + username.hashCode(),
            username,
            username + "@example.com",
            Arrays.asList(roles.toArray(new String[0])),
            getPermissionsForRoles(roles)
        );
    }
    
    private java.util.List<String> getPermissionsForRoles(Set<String> roles) {
        java.util.List<String> permissions = new java.util.ArrayList<>();
        if (roles.contains("USER")) {
            permissions.add("read:secrets");
            permissions.add("read:profile");
        }
        if (roles.contains("ADMIN")) {
            permissions.add("write:all");
            permissions.add("delete:all");
            permissions.add("admin:access");
        }
        return permissions;
    }
}
