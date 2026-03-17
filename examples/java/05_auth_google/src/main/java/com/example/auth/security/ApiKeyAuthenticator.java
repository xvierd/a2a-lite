package com.example.auth.security;

import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * API Key authenticator - validates API keys and returns associated roles.
 * Demonstrates API key authentication in the header or query parameter.
 */
public class ApiKeyAuthenticator {
    
    // In-memory API key store - in production, use a secure database
    private final Map<String, ApiKeyInfo> apiKeyStore = new ConcurrentHashMap<>();
    
    public ApiKeyAuthenticator() {
        // Initialize with some demo API keys
        apiKeyStore.put("ak_user_12345", new ApiKeyInfo("user1", Set.of("USER")));
        apiKeyStore.put("ak_admin_67890", new ApiKeyInfo("admin1", Set.of("ADMIN", "USER")));
        apiKeyStore.put("ak_guest_abcde", new ApiKeyInfo("guest1", Set.of("GUEST")));
    }
    
    /**
     * Validate an API key and return authentication result.
     * Supports both header-based and query parameter-based API keys.
     */
    public AuthenticationResult authenticate(String apiKey) {
        if (apiKey == null || apiKey.isEmpty()) {
            return AuthenticationResult.failed("API key is missing");
        }
        
        ApiKeyInfo info = apiKeyStore.get(apiKey);
        if (info == null) {
            return AuthenticationResult.failed("Invalid API key");
        }
        
        return AuthenticationResult.success(info.username, info.roles);
    }
    
    /**
     * Check if API key has required role.
     */
    public boolean hasRole(String apiKey, String requiredRole) {
        ApiKeyInfo info = apiKeyStore.get(apiKey);
        if (info == null) return false;
        return info.roles.contains(requiredRole);
    }
    
    private static class ApiKeyInfo {
        final String username;
        final Set<String> roles;
        
        ApiKeyInfo(String username, Set<String> roles) {
            this.username = username;
            this.roles = roles;
        }
    }
    
    public static class AuthenticationResult {
        private final boolean success;
        private final String username;
        private final Set<String> roles;
        private final String errorMessage;
        
        private AuthenticationResult(boolean success, String username, 
                                     Set<String> roles, String errorMessage) {
            this.success = success;
            this.username = username;
            this.roles = roles;
            this.errorMessage = errorMessage;
        }
        
        static AuthenticationResult success(String username, Set<String> roles) {
            return new AuthenticationResult(true, username, roles, null);
        }
        
        static AuthenticationResult failed(String errorMessage) {
            return new AuthenticationResult(false, null, null, errorMessage);
        }
        
        public boolean isSuccess() { return success; }
        public String getUsername() { return username; }
        public Set<String> getRoles() { return roles; }
        public String getErrorMessage() { return errorMessage; }
    }
}
