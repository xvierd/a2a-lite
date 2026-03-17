package com.example.auth;

import io.javalin.Javalin;
import io.javalin.http.Context;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;

import java.util.*;

/**
 * SecureAgentServer - A2A Agent with authentication using Javalin.
 * 
 * This example demonstrates API Key and Bearer token authentication.
 */
public class SecureAgentServer {
    
    private static final int PORT = 8080;
    private static final ObjectMapper mapper = new ObjectMapper();
    
    // Valid API keys and their roles
    private static final Map<String, Set<String>> API_KEYS = Map.of(
        "ak_user_12345", Set.of("USER"),
        "ak_admin_67890", Set.of("ADMIN", "USER"),
        "ak_guest_abcde", Set.of("GUEST")
    );
    
    // Valid bearer tokens and their roles
    private static final Map<String, Set<String>> BEARER_TOKENS = Map.of(
        "eyJhbGciOiJIUzI1NiJ9.user", Set.of("USER"),
        "eyJhbGciOiJIUzI1NiJ9.admin", Set.of("ADMIN", "USER"),
        "eyJhbGciOiJIUzI1NiJ9.service", Set.of("SERVICE")
    );
    
    public static void main(String[] args) {
        System.out.println("=".repeat(70));
        System.out.println("Secure Agent Server - A2A with Authentication");
        System.out.println("=".repeat(70));
        
        Javalin app = Javalin.create(config -> {
            config.showJavalinBanner = false;
        });
        
        // CORS configuration
        app.before(ctx -> {
            ctx.header("Access-Control-Allow-Origin", "*");
            ctx.header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS");
            ctx.header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key");
        });
        
        // Agent Card endpoint with security schemes
        app.get("/.well-known/agent.json", ctx -> {
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(createAgentCard()));
        });
        
        // Skill endpoints
        app.post("/skills/get_secret", ctx -> handleGetSecret(ctx));
        app.post("/skills/get_user_info", ctx -> handleGetUserInfo(ctx));
        app.post("/skills/admin_only", ctx -> handleAdminOnly(ctx));
        
        // Health check
        app.get("/health", ctx -> ctx.json(Map.of("status", "healthy")));
        
        // Main A2A message endpoint
        app.post("/", ctx -> handleMessage(ctx));
        
        System.out.println("Secure Agent Server started on port " + PORT);
        System.out.println("Security Schemes configured: apiKeyHeader, apiKeyQuery, bearerAuth");
        System.out.println("=".repeat(70));
        
        app.start(PORT);
    }
    
    private static ObjectNode createAgentCard() {
        ObjectNode card = mapper.createObjectNode();
        card.put("name", "Secure Authentication Agent");
        card.put("description", "Demonstrates authentication with A2A");
        card.put("version", "1.0.0");
        card.put("url", "http://localhost:" + PORT);
        
        // Security schemes definition
        ObjectNode schemes = mapper.createObjectNode();
        
        ObjectNode apiKeyHeader = mapper.createObjectNode();
        apiKeyHeader.put("type", "apiKey");
        apiKeyHeader.put("in", "header");
        apiKeyHeader.put("name", "X-API-Key");
        schemes.set("apiKeyHeader", apiKeyHeader);
        
        ObjectNode apiKeyQuery = mapper.createObjectNode();
        apiKeyQuery.put("type", "apiKey");
        apiKeyQuery.put("in", "query");
        apiKeyQuery.put("name", "api_key");
        schemes.set("apiKeyQuery", apiKeyQuery);
        
        ObjectNode bearerAuth = mapper.createObjectNode();
        bearerAuth.put("type", "http");
        bearerAuth.put("scheme", "bearer");
        bearerAuth.put("bearerFormat", "JWT");
        schemes.set("bearerAuth", bearerAuth);
        
        card.set("securitySchemes", schemes);
        
        // Skills
        ArrayNode skills = mapper.createArrayNode();
        
        ObjectNode skill1 = mapper.createObjectNode();
        skill1.put("id", "get_secret");
        skill1.put("name", "Get Secret");
        skill1.put("description", "Returns a secret message for authenticated users");
        skills.add(skill1);
        
        ObjectNode skill2 = mapper.createObjectNode();
        skill2.put("id", "get_user_info");
        skill2.put("name", "Get User Info");
        skill2.put("description", "Returns user information (USER or ADMIN required)");
        skills.add(skill2);
        
        ObjectNode skill3 = mapper.createObjectNode();
        skill3.put("id", "admin_only");
        skill3.put("name", "Admin Only");
        skill3.put("description", "Administrative operations (ADMIN only)");
        skills.add(skill3);
        
        card.set("skills", skills);
        
        return card;
    }
    
    private static void handleMessage(Context ctx) {
        try {
            AuthUser user = authenticate(ctx);
            JsonNode request = mapper.readTree(ctx.body());
            
            String skill = request.path("params").path("skill").asText();
            Object result = switch (skill) {
                case "get_secret" -> getSecret(user);
                case "get_user_info" -> getUserInfo(user);
                case "admin_only" -> adminOnly(user, request.path("params").path("operation").asText());
                default -> throw new IllegalArgumentException("Unknown skill: " + skill);
            };
            
            ObjectNode response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.set("id", request.get("id"));
            response.set("result", mapper.valueToTree(result));
            
            ctx.json(response);
        } catch (SecurityException e) {
            ctx.status(401);
            ctx.json(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            ctx.status(500);
            ctx.json(Map.of("error", e.getMessage()));
        }
    }
    
    private static void handleGetSecret(Context ctx) {
        try {
            AuthUser user = authenticate(ctx);
            ctx.json(getSecret(user));
        } catch (SecurityException e) {
            ctx.status(401);
            ctx.json(Map.of("error", e.getMessage()));
        }
    }
    
    private static void handleGetUserInfo(Context ctx) {
        try {
            AuthUser user = authenticate(ctx);
            if (!user.hasRole("USER")) {
                throw new SecurityException("USER role required");
            }
            ctx.json(getUserInfo(user));
        } catch (SecurityException e) {
            ctx.status(403);
            ctx.json(Map.of("error", e.getMessage()));
        }
    }
    
    private static void handleAdminOnly(Context ctx) {
        try {
            AuthUser user = authenticate(ctx);
            if (!user.hasRole("ADMIN")) {
                throw new SecurityException("ADMIN role required");
            }
            JsonNode body = mapper.readTree(ctx.body());
            String operation = body.path("operation").asText("status");
            ctx.json(adminOnly(user, operation));
        } catch (SecurityException e) {
            ctx.status(403);
            ctx.json(Map.of("error", e.getMessage()));
        } catch (Exception e) {
            ctx.status(500);
            ctx.json(Map.of("error", e.getMessage()));
        }
    }
    
    private static AuthUser authenticate(Context ctx) {
        String apiKey = ctx.header("X-API-Key");
        if (apiKey == null) {
            apiKey = ctx.queryParam("api_key");
        }
        
        String authHeader = ctx.header("Authorization");
        String bearerToken = null;
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            bearerToken = authHeader.substring(7);
        }
        
        if (apiKey != null && API_KEYS.containsKey(apiKey)) {
            return new AuthUser("apikey_" + apiKey.substring(apiKey.length() - 5), API_KEYS.get(apiKey));
        }
        
        if (bearerToken != null && BEARER_TOKENS.containsKey(bearerToken)) {
            return new AuthUser("token_" + bearerToken.substring(bearerToken.length() - 5), BEARER_TOKENS.get(bearerToken));
        }
        
        throw new SecurityException("Authentication required");
    }
    
    private static Map<String, Object> getSecret(AuthUser user) {
        return Map.of(
            "secret", "The secret is: Authentication works!",
            "accessedBy", user.username(),
            "role", String.join(", ", user.roles())
        );
    }
    
    private static Map<String, Object> getUserInfo(AuthUser user) {
        return Map.of(
            "userId", "usr_" + user.username().hashCode(),
            "username", user.username(),
            "email", user.username() + "@example.com",
            "roles", user.roles(),
            "permissions", getPermissions(user.roles())
        );
    }
    
    private static Map<String, Object> adminOnly(AuthUser user, String operation) {
        String message = switch (operation) {
            case "reload" -> "Configuration reloaded";
            case "clear-cache" -> "Cache cleared";
            default -> "System status: All services operational";
        };
        return Map.of(
            "message", message,
            "adminAction", operation,
            "performedBy", user.username()
        );
    }
    
    private static Set<String> getPermissions(Set<String> roles) {
        Set<String> perms = new HashSet<>();
        if (roles.contains("USER")) {
            perms.add("read:secrets");
            perms.add("read:profile");
        }
        if (roles.contains("ADMIN")) {
            perms.add("write:all");
            perms.add("delete:all");
            perms.add("admin:access");
        }
        return perms;
    }
    
    record AuthUser(String username, Set<String> roles) {
        boolean hasRole(String role) {
            return roles.contains(role);
        }
    }
}
