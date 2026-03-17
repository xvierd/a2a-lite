package com.example.auth.security;

import java.util.HashMap;
import java.util.Map;

/**
 * SecuritySchemes - configures security schemes according to A2A specification.
 * This class defines the security requirements for the agent.
 */
public class SecuritySchemes {
    
    /**
     * Security scheme types supported by A2A specification.
     */
    public enum SchemeType {
        API_KEY,
        BEARER,
        BASIC,
        OAUTH2
    }
    
    /**
     * API Key location - header or query parameter.
     */
    public enum ApiKeyLocation {
        HEADER,
        QUERY
    }
    
    private final Map<String, SecurityScheme> schemes = new HashMap<>();
    
    public SecuritySchemes() {
        // Configure API Key in header
        schemes.put("apiKeyHeader", SecurityScheme.apiKey()
            .name("X-API-Key")
            .location(ApiKeyLocation.HEADER)
            .description("API key authentication via HTTP header")
            .build());
        
        // Configure API Key in query parameter
        schemes.put("apiKeyQuery", SecurityScheme.apiKey()
            .name("api_key")
            .location(ApiKeyLocation.QUERY)
            .description("API key authentication via query parameter")
            .build());
        
        // Configure Bearer token (OAuth2 / JWT)
        schemes.put("bearerAuth", SecurityScheme.bearer()
            .format("JWT")
            .description("Bearer token authentication (JWT)")
            .build());
    }
    
    public Map<String, SecurityScheme> getSchemes() {
        return schemes;
    }
    
    public SecurityScheme getScheme(String name) {
        return schemes.get(name);
    }
    
    /**
     * Security scheme definition.
     */
    public static class SecurityScheme {
        private final SchemeType type;
        private final String name;
        private final String description;
        private final ApiKeyLocation location;  // For API key
        private final String format;            // For Bearer
        
        private SecurityScheme(Builder builder) {
            this.type = builder.type;
            this.name = builder.name;
            this.description = builder.description;
            this.location = builder.location;
            this.format = builder.format;
        }
        
        public static Builder apiKey() {
            return new Builder(SchemeType.API_KEY);
        }
        
        public static Builder bearer() {
            return new Builder(SchemeType.BEARER);
        }
        
        public SchemeType getType() { return type; }
        public String getName() { return name; }
        public String getDescription() { return description; }
        public ApiKeyLocation getLocation() { return location; }
        public String getFormat() { return format; }
        
        public static class Builder {
            private final SchemeType type;
            private String name;
            private String description;
            private ApiKeyLocation location;
            private String format;
            
            private Builder(SchemeType type) {
                this.type = type;
            }
            
            public Builder name(String name) {
                this.name = name;
                return this;
            }
            
            public Builder description(String description) {
                this.description = description;
                return this;
            }
            
            public Builder location(ApiKeyLocation location) {
                this.location = location;
                return this;
            }
            
            public Builder format(String format) {
                this.format = format;
                return this;
            }
            
            public SecurityScheme build() {
                return new SecurityScheme(this);
            }
        }
    }
    
    /**
     * Security requirement for a skill.
     */
    public static class SecurityRequirement {
        private final String schemeName;
        private final String[] roles;
        
        public SecurityRequirement(String schemeName, String... roles) {
            this.schemeName = schemeName;
            this.roles = roles != null ? roles : new String[0];
        }
        
        public String getSchemeName() { return schemeName; }
        public String[] getRoles() { return roles; }
        
        public boolean requiresRole(String role) {
            if (roles.length == 0) return true; // No specific role required
            for (String r : roles) {
                if (r.equals(role)) return true;
            }
            return false;
        }
    }
}
