package com.example.auth.security;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Bearer Token authenticator - validates JWT-style bearer tokens.
 * Demonstrates OAuth2-style Bearer token authentication.
 */
public class BearerTokenAuthenticator {
    
    // In-memory token store - in production, use JWT validation or OAuth2 introspection
    private final Map<String, TokenInfo> tokenStore = new ConcurrentHashMap<>();
    
    public BearerTokenAuthenticator() {
        // Initialize with some demo tokens
        tokenStore.put("eyJhbGciOiJIUzI1NiJ9.user", 
            new TokenInfo("john_doe", Set.of("USER"), 3600));
        tokenStore.put("eyJhbGciOiJIUzI1NiJ9.admin", 
            new TokenInfo("jane_admin", Set.of("ADMIN", "USER"), 3600));
        tokenStore.put("eyJhbGciOiJIUzI1NiJ9.service", 
            new TokenInfo("service_account", Set.of("SERVICE"), 7200));
    }
    
    /**
     * Validate a Bearer token and return authentication result.
     * Expects token without the "Bearer " prefix.
     */
    public AuthenticationResult authenticate(String token) {
        if (token == null || token.isEmpty()) {
            return AuthenticationResult.failed("Bearer token is missing");
        }
        
        // Remove "Bearer " prefix if present
        if (token.startsWith("Bearer ")) {
            token = token.substring(7);
        }
        
        TokenInfo info = tokenStore.get(token);
        if (info == null) {
            return AuthenticationResult.failed("Invalid or expired token");
        }
        
        // In real implementation, check token expiration here
        return AuthenticationResult.success(info.username, info.roles, token);
    }
    
    /**
     * Check if token has required role.
     */
    public boolean hasRole(String token, String requiredRole) {
        // Remove "Bearer " prefix if present
        if (token != null && token.startsWith("Bearer ")) {
            token = token.substring(7);
        }
        TokenInfo info = tokenStore.get(token);
        if (info == null) return false;
        return info.roles.contains(requiredRole);
    }
    
    private static class TokenInfo {
        final String username;
        final Set<String> roles;
        final long expiresIn;
        final long createdAt;
        
        TokenInfo(String username, Set<String> roles, long expiresIn) {
            this.username = username;
            this.roles = roles;
            this.expiresIn = expiresIn;
            this.createdAt = System.currentTimeMillis();
        }
        
        boolean isExpired() {
            return System.currentTimeMillis() > createdAt + (expiresIn * 1000);
        }
    }
    
    public static class AuthenticationResult {
        private final boolean success;
        private final String username;
        private final Set<String> roles;
        private final String token;
        private final String errorMessage;
        
        private AuthenticationResult(boolean success, String username, 
                                     Set<String> roles, String token, String errorMessage) {
            this.success = success;
            this.username = username;
            this.roles = roles;
            this.token = token;
            this.errorMessage = errorMessage;
        }
        
        static AuthenticationResult success(String username, Set<String> roles, String token) {
            return new AuthenticationResult(true, username, roles, token, null);
        }
        
        static AuthenticationResult failed(String errorMessage) {
            return new AuthenticationResult(false, null, null, null, errorMessage);
        }
        
        public boolean isSuccess() { return success; }
        public String getUsername() { return username; }
        public Set<String> getRoles() { return roles; }
        public String getToken() { return token; }
        public String getErrorMessage() { return errorMessage; }
    }
}
