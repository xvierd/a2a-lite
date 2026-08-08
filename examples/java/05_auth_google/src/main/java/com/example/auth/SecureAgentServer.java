package com.example.auth;

import io.javalin.Javalin;
import io.javalin.http.Context;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;

import java.util.*;

/**
 * SecureAgentServer - A2A protocol v1.0 with authentication, "from scratch" (Java)
 *
 * This example implements the A2A v1.0 wire protocol by hand with Javalin +
 * Jackson — no SDK. It demonstrates API Key and Bearer token authentication.
 * For the official Java SDK approach see packages/java.
 */
public class SecureAgentServer {

    private static final int PORT = 8080;
    private static final ObjectMapper mapper = new ObjectMapper();
    private static final String A2A_VERSION = "1.0";
    
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
        System.out.println("Secure Agent Server - A2A v1.0 with Authentication (from scratch)");
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
        
        // Agent Card endpoint with security schemes (A2A v1.0 discovery)
        app.get("/.well-known/agent-card.json", ctx -> {
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
    
    /**
     * Create the A2A v1.0 agent card for discovery.
     */
    private static ObjectNode createAgentCard() {
        ObjectNode card = mapper.createObjectNode();
        card.put("name", "Secure Authentication Agent");
        card.put("description", "Demonstrates authentication with A2A v1.0 (from scratch, no SDK)");
        card.put("version", "1.0.0");

        // v1.0: interfaces replace the root "url" field
        ArrayNode interfaces = mapper.createArrayNode();
        ObjectNode iface = mapper.createObjectNode();
        iface.put("url", "http://localhost:" + PORT + "/");
        iface.put("protocolBinding", "JSONRPC");
        iface.put("protocolVersion", "1.0");
        interfaces.add(iface);
        card.set("supportedInterfaces", interfaces);

        // Security schemes definition (v1.0)
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

        // v1.0: security requirements reference the schemes above
        ArrayNode requirements = mapper.createArrayNode();
        for (String schemeName : new String[]{"apiKeyHeader", "apiKeyQuery", "bearerAuth"}) {
            ObjectNode req = mapper.createObjectNode();
            req.set(schemeName, mapper.createArrayNode());
            requirements.add(req);
        }
        card.set("securityRequirements", requirements);

        // Skills
        ArrayNode skills = mapper.createArrayNode();

        ObjectNode skill1 = mapper.createObjectNode();
        skill1.put("id", "get_secret");
        skill1.put("name", "Get Secret");
        skill1.put("description", "Returns a secret message for authenticated users");
        ArrayNode tags1 = mapper.createArrayNode();
        tags1.add("auth");
        tags1.add("secret");
        skill1.set("tags", tags1);
        skills.add(skill1);

        ObjectNode skill2 = mapper.createObjectNode();
        skill2.put("id", "get_user_info");
        skill2.put("name", "Get User Info");
        skill2.put("description", "Returns user information (USER or ADMIN required)");
        ArrayNode tags2 = mapper.createArrayNode();
        tags2.add("auth");
        tags2.add("user");
        skill2.set("tags", tags2);
        skills.add(skill2);

        ObjectNode skill3 = mapper.createObjectNode();
        skill3.put("id", "admin_only");
        skill3.put("name", "Admin Only");
        skill3.put("description", "Administrative operations (ADMIN only)");
        ArrayNode tags3 = mapper.createArrayNode();
        tags3.add("auth");
        tags3.add("admin");
        skill3.set("tags", tags3);
        skills.add(skill3);

        card.set("skills", skills);

        // Capabilities
        ObjectNode capabilities = mapper.createObjectNode();
        capabilities.put("streaming", false);
        capabilities.put("pushNotifications", false);
        card.set("capabilities", capabilities);

        // Input/output modes
        ArrayNode modes = mapper.createArrayNode();
        modes.add("text/plain");
        card.set("defaultInputModes", modes);
        card.set("defaultOutputModes", modes);

        return card;
    }

    /**
     * Handle incoming A2A v1.0 JSON-RPC messages (SendMessage).
     */
    private static void handleMessage(Context ctx) {
        try {
            // A2A v1.0: echo the protocol version on every RPC response
            ctx.header("A2A-Version", A2A_VERSION);

            AuthUser user = authenticate(ctx);
            JsonNode request = mapper.readTree(ctx.body());

            // Validate JSON-RPC
            if (!request.has("jsonrpc") || !"2.0".equals(request.get("jsonrpc").asText())) {
                sendError(ctx, request.get("id"), -32600, "Invalid JSON-RPC request");
                return;
            }

            String method = request.has("method") ? request.get("method").asText() : "";
            if (!"SendMessage".equals(method)) {
                sendError(ctx, request.get("id"), -32601, "Method not found: " + method);
                return;
            }

            // Extract skill call from the message text part (v1.0 parts: {"text": ...})
            JsonNode parts = request.path("params").path("message").path("parts");
            String skillCallJson = null;
            if (parts.isArray()) {
                for (JsonNode part : parts) {
                    if (part.has("text")) {
                        skillCallJson = part.get("text").asText();
                        break;
                    }
                }
            }
            if (skillCallJson == null) {
                sendError(ctx, request.get("id"), -32602, "No text part found in message");
                return;
            }

            // Parse skill call: {"skill": "<name>", "params": {...}}
            JsonNode skillCall = mapper.readTree(skillCallJson);
            String skill = skillCall.path("skill").asText();
            JsonNode skillParams = skillCall.path("params");

            Object result = switch (skill) {
                case "get_secret" -> getSecret(user);
                case "get_user_info" -> getUserInfo(user);
                case "admin_only" -> adminOnly(user, skillParams.path("operation").asText("status"));
                default -> throw new IllegalArgumentException("Unknown skill: " + skill);
            };

            // v1.0 response: {"result": {"message": {...}}}
            ObjectNode response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.set("id", request.get("id"));

            ObjectNode resultObj = mapper.createObjectNode();
            ObjectNode messageObj = mapper.createObjectNode();
            messageObj.put("messageId", java.util.UUID.randomUUID().toString());
            messageObj.put("role", "ROLE_AGENT");
            ArrayNode responseParts = mapper.createArrayNode();
            ObjectNode textPart = mapper.createObjectNode();
            textPart.put("text", mapper.writeValueAsString(result));
            responseParts.add(textPart);
            messageObj.set("parts", responseParts);
            resultObj.set("message", messageObj);
            response.set("result", resultObj);

            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(response));
        } catch (SecurityException e) {
            sendError(ctx, null, -32001, e.getMessage(), 401);
        } catch (IllegalArgumentException e) {
            sendError(ctx, null, -32000, e.getMessage());
        } catch (Exception e) {
            sendError(ctx, null, -32603, "Internal error: " + e.getMessage());
        }
    }

    /**
     * Send JSON-RPC error response (HTTP 400).
     */
    private static void sendError(Context ctx, JsonNode id, int code, String message) {
        sendError(ctx, id, code, message, 400);
    }

    /**
     * Send JSON-RPC error response with a specific HTTP status.
     */
    private static void sendError(Context ctx, JsonNode id, int code, String message, int httpStatus) {
        try {
            ObjectNode error = mapper.createObjectNode();
            error.put("jsonrpc", "2.0");
            if (id != null) {
                error.set("id", id);
            } else {
                error.putNull("id");
            }
            ObjectNode errorObj = mapper.createObjectNode();
            errorObj.put("code", code);
            errorObj.put("message", message);
            error.set("error", errorObj);

            ctx.status(httpStatus);
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(error));
        } catch (Exception e) {
            ctx.status(500);
            ctx.result("Internal error");
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
