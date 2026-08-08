package com.example.calculator;

import io.javalin.Javalin;
import io.javalin.http.Context;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;

/**
 * Calculator Agent - A2A protocol v1.0 "from scratch" (Java)
 *
 * This example implements the A2A v1.0 wire protocol by hand with Javalin +
 * Jackson — no SDK. For the official Java SDK approach see packages/java.
 */
public class CalculatorAgent {

    private static final int PORT = 8788;
    private static final ObjectMapper mapper = new ObjectMapper();
    private static final String A2A_VERSION = "1.0";

    public static void main(String[] args) {
        System.out.println("=".repeat(60));
        System.out.println("Calculator Agent - A2A v1.0 from scratch (Java)");
        System.out.println("=".repeat(60));

        CalculatorSkill calculator = new CalculatorSkill();
        MessageHandler handler = new MessageHandler(calculator);
        ObjectNode agentCard = createAgentCard();

        Javalin app = Javalin.create(config -> {
            config.showJavalinBanner = false;
        });

        // Agent card endpoint (A2A v1.0 discovery)
        app.get("/.well-known/agent-card.json", ctx -> {
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(agentCard));
        });

        // Health check
        app.get("/", ctx -> {
            ObjectNode health = mapper.createObjectNode();
            health.put("status", "healthy");
            health.put("agent", "CalculatorAgent");
            ctx.json(health);
        });

        // Main A2A message endpoint
        app.post("/", ctx -> {
            handleMessage(ctx, handler);
        });

        System.out.println("Agent: CalculatorAgent");
        System.out.println("Skills: add, subtract, multiply, divide, power");
        System.out.println("-".repeat(60));
        System.out.println("Starting server on http://localhost:" + PORT);
        System.out.println("Agent card: http://localhost:" + PORT + "/.well-known/agent-card.json");
        System.out.println("=".repeat(60));

        app.start(PORT);
    }

    /**
     * Create the A2A v1.0 agent card for discovery.
     */
    private static ObjectNode createAgentCard() {
        ObjectNode card = mapper.createObjectNode();
        card.put("name", "CalculatorAgent");
        card.put("description", "A calculator agent with arithmetic operations (A2A v1.0 from scratch)");
        card.put("version", "1.0.0");

        // v1.0: interfaces replace the root "url" field
        ArrayNode interfaces = mapper.createArrayNode();
        ObjectNode iface = mapper.createObjectNode();
        iface.put("url", "http://localhost:" + PORT + "/");
        iface.put("protocolBinding", "JSONRPC");
        iface.put("protocolVersion", "1.0");
        interfaces.add(iface);
        card.set("supportedInterfaces", interfaces);

        // Skills array (v1.0: each skill carries an "id" plus name/description/tags)
        ArrayNode skills = mapper.createArrayNode();
        String[] skillNames = {"add", "subtract", "multiply", "divide", "power"};

        for (String skillName : skillNames) {
            ObjectNode skill = mapper.createObjectNode();
            skill.put("id", skillName);
            skill.put("name", skillName);
            skill.put("description", skillName + " operation");
            ArrayNode tags = mapper.createArrayNode();
            tags.add("arithmetic");
            skill.set("tags", tags);
            skills.add(skill);
        }
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
     * Handle incoming A2A messages.
     */
    private static void handleMessage(Context ctx, MessageHandler handler) {
        try {
            // A2A v1.0: echo the protocol version on every response
            ctx.header("A2A-Version", A2A_VERSION);

            String body = ctx.body();
            ObjectNode request = (ObjectNode) mapper.readTree(body);

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

            // Process message
            ObjectNode response = handler.handle(request);
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(response));

        } catch (Exception e) {
            sendError(ctx, null, -32603, "Internal error: " + e.getMessage());
        }
    }

    /**
     * Send JSON-RPC error response.
     */
    private static void sendError(Context ctx, com.fasterxml.jackson.databind.JsonNode id,
                                   int code, String message) {
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

            ctx.status(400);
            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(error));
        } catch (Exception e) {
            ctx.status(500);
            ctx.result("Internal error");
        }
    }
}
