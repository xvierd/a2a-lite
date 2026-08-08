package com.example.streaming;

import io.javalin.Javalin;
import io.javalin.http.Context;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.example.streaming.sse.CollectingEmitter;
import com.example.streaming.sse.SseEventEmitter;
import com.example.streaming.sse.StreamEmitter;
import com.example.streaming.skills.*;

import java.util.UUID;

/**
 * Streaming Agent - A2A protocol v1.0 "from scratch" (Java)
 *
 * This example implements the A2A v1.0 wire protocol by hand with Javalin +
 * Jackson — no SDK. For the official Java SDK approach see packages/java
 * (LiteAgentExecutor / Quarkus integration).
 *
 * Features:
 * - Agent card at /.well-known/agent-card.json with streaming=true
 * - SendMessage (synchronous) and SendStreamingMessage (SSE) JSON-RPC methods
 * - v1.0 SSE events: task first, then statusUpdate / artifactUpdate
 * - Multiple streaming skills: chat, count, story, progress
 */
public class StreamingAgent {

    private static final int PORT = 8787;
    private static final ObjectMapper mapper = new ObjectMapper();
    private static final String A2A_VERSION = "1.0";

    // Skill handlers
    private static final ChatSkill chatSkill = new ChatSkill();
    private static final CountSkill countSkill = new CountSkill();
    private static final StorySkill storySkill = new StorySkill();
    private static final ProgressSkill progressSkill = new ProgressSkill();

    public static void main(String[] args) {
        System.out.println("=".repeat(70));
        System.out.println("Streaming Agent - A2A v1.0 from scratch (Java)");
        System.out.println("=".repeat(70));

        // Create agent card with streaming capabilities
        ObjectNode agentCard = createAgentCard();

        // Setup Javalin server
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
            health.put("agent", "StreamingAgent");
            health.put("streaming", true);
            ctx.json(health);
        });

        // Main A2A JSON-RPC endpoint (SendMessage / SendStreamingMessage)
        app.post("/", ctx -> {
            handleRpc(ctx);
        });

        System.out.println("Agent: StreamingAgent");
        System.out.println("Skills: chat, count, story, progress");
        System.out.println("Capabilities: streaming=true");
        System.out.println("-".repeat(70));
        System.out.println("Starting server on http://localhost:" + PORT);
        System.out.println("Agent card: http://localhost:" + PORT + "/.well-known/agent-card.json");
        System.out.println("=".repeat(70));

        app.start(PORT);
    }

    /**
     * Create the A2A v1.0 agent card with streaming capabilities.
     */
    private static ObjectNode createAgentCard() {
        ObjectNode card = mapper.createObjectNode();
        card.put("name", "StreamingAgent");
        card.put("description", "Streaming agent demonstrating SSE (A2A v1.0 from scratch)");
        card.put("version", "1.0.0");

        // v1.0: interfaces replace the root "url" field
        ArrayNode interfaces = mapper.createArrayNode();
        ObjectNode iface = mapper.createObjectNode();
        iface.put("url", "http://localhost:" + PORT + "/");
        iface.put("protocolBinding", "JSONRPC");
        iface.put("protocolVersion", "1.0");
        interfaces.add(iface);
        card.set("supportedInterfaces", interfaces);

        // Skills array
        ArrayNode skills = mapper.createArrayNode();
        skills.add(createSkillCard("chat", "Interactive chat with streaming responses",
            new String[]{"chat", "streaming"}));
        skills.add(createSkillCard("count", "Count to a number with progress updates",
            new String[]{"count", "progress"}));
        skills.add(createSkillCard("story", "Generate a story word by word",
            new String[]{"story", "generation"}));
        skills.add(createSkillCard("progress", "Show progress updates for long tasks",
            new String[]{"progress", "tasks"}));
        card.set("skills", skills);

        // Capabilities - IMPORTANT: streaming=true
        ObjectNode capabilities = mapper.createObjectNode();
        capabilities.put("streaming", true);
        capabilities.put("pushNotifications", false);
        card.set("capabilities", capabilities);

        // Input/output modes
        ArrayNode modes = mapper.createArrayNode();
        modes.add("text/plain");
        card.set("defaultInputModes", modes);
        card.set("defaultOutputModes", modes);

        return card;
    }

    private static ObjectNode createSkillCard(String id, String description, String[] tags) {
        ObjectNode skill = mapper.createObjectNode();
        skill.put("id", id);
        skill.put("name", id);
        skill.put("description", description);
        ArrayNode tagsNode = mapper.createArrayNode();
        for (String tag : tags) {
            tagsNode.add(tag);
        }
        skill.set("tags", tagsNode);
        return skill;
    }

    /**
     * Handle incoming A2A JSON-RPC requests.
     */
    private static void handleRpc(Context ctx) {
        // A2A v1.0: echo the protocol version on every response
        ctx.header("A2A-Version", A2A_VERSION);

        ObjectNode request;
        try {
            request = (ObjectNode) mapper.readTree(ctx.body());
        } catch (Exception e) {
            sendError(ctx, null, -32700, "Parse error: " + e.getMessage());
            return;
        }

        // Validate JSON-RPC
        if (!request.has("jsonrpc") || !"2.0".equals(request.get("jsonrpc").asText())) {
            sendError(ctx, request.get("id"), -32600, "Invalid JSON-RPC request");
            return;
        }

        String method = request.has("method") ? request.get("method").asText() : "";
        switch (method) {
            case "SendMessage" -> handleSendMessage(ctx, request);
            case "SendStreamingMessage" -> handleSendStreamingMessage(ctx, request);
            default -> sendError(ctx, request.get("id"), -32601, "Method not found: " + method);
        }
    }

    /**
     * SendMessage: run the skill synchronously and return an agent message.
     */
    private static void handleSendMessage(Context ctx, ObjectNode request) {
        try {
            SkillCall call = extractSkillCall(request);

            // Run the skill, buffering its streamed output
            CollectingEmitter collector = new CollectingEmitter();
            executeSkill(call.skill, call.params, collector);

            ObjectNode response = mapper.createObjectNode();
            response.put("jsonrpc", "2.0");
            response.set("id", request.get("id"));

            ObjectNode message = mapper.createObjectNode();
            message.put("messageId", UUID.randomUUID().toString());
            message.put("role", "ROLE_AGENT");
            ArrayNode parts = mapper.createArrayNode();
            ObjectNode textPart = mapper.createObjectNode();
            textPart.put("text", collector.getResult());
            parts.add(textPart);
            message.set("parts", parts);

            ObjectNode result = mapper.createObjectNode();
            result.set("message", message);
            response.set("result", result);

            ctx.contentType("application/json");
            ctx.result(mapper.writeValueAsString(response));

        } catch (IllegalArgumentException e) {
            sendError(ctx, request.get("id"), -32602, e.getMessage());
        } catch (Exception e) {
            sendError(ctx, request.get("id"), -32603, "Internal error: " + e.getMessage());
        }
    }

    /**
     * SendStreamingMessage: stream v1.0 SSE events on this HTTP response.
     *
     * The first event is always the task, followed by statusUpdate and
     * artifactUpdate events. There is no `final` field — closing the stream
     * signals terminality.
     */
    private static void handleSendStreamingMessage(Context ctx, ObjectNode request) {
        SkillCall call;
        try {
            call = extractSkillCall(request);
        } catch (IllegalArgumentException e) {
            sendError(ctx, request.get("id"), -32602, e.getMessage());
            return;
        }

        // SSE response headers (must be set before the writer is obtained)
        ctx.status(200);
        ctx.header("Content-Type", "text/event-stream");
        ctx.header("Cache-Control", "no-cache");
        ctx.header("Connection", "keep-alive");
        ctx.header("X-Accel-Buffering", "no"); // Disable proxy buffering

        String taskId = UUID.randomUUID().toString();
        String contextId = UUID.randomUUID().toString();

        System.out.println("[SSE] Starting stream: task=" + taskId + ", skill=" + call.skill);

        SseEventEmitter emitter = new SseEventEmitter(ctx, taskId, contextId);
        try {
            // v1.0: the task is always the first event
            emitter.sendTask();
            executeSkill(call.skill, call.params, emitter);
        } catch (Exception e) {
            emitter.sendError("Internal error: " + e.getMessage());
        }

        System.out.println("[SSE] Stream ended: " + taskId);
    }

    /**
     * Execute a skill by name, streaming its output through the emitter.
     */
    private static void executeSkill(String skill, ObjectNode params, StreamEmitter emitter) {
        switch (skill) {
            case "chat" -> chatSkill.stream(params, emitter);
            case "count" -> countSkill.stream(params, emitter);
            case "story" -> storySkill.stream(params, emitter);
            case "progress" -> progressSkill.stream(params, emitter);
            default -> emitter.sendError("Unknown skill: " + skill);
        }
    }

    /**
     * Extract the skill call from the message parts. v1.0 text parts are
     * {"text": ...} with no kind/type; the text carries a JSON skill call
     * of the form {"skill": "<name>", "params": {...}}.
     */
    private static SkillCall extractSkillCall(ObjectNode request) {
        ObjectNode params = request.has("params") && request.get("params").isObject()
            ? (ObjectNode) request.get("params") : null;
        ObjectNode message = params != null && params.has("message") && params.get("message").isObject()
            ? (ObjectNode) params.get("message") : null;
        if (message == null || !message.has("parts") || !message.get("parts").isArray()) {
            throw new IllegalArgumentException("Invalid params: expected params.message.parts");
        }

        String skillCallJson = null;
        for (var part : (ArrayNode) message.get("parts")) {
            if (part.isObject() && part.has("text")) {
                skillCallJson = part.get("text").asText();
                break;
            }
        }
        if (skillCallJson == null) {
            throw new IllegalArgumentException("No text part found in message");
        }

        ObjectNode skillCall;
        try {
            skillCall = (ObjectNode) mapper.readTree(skillCallJson);
        } catch (Exception e) {
            throw new IllegalArgumentException("Text part is not a valid skill call JSON");
        }
        if (!skillCall.has("skill")) {
            throw new IllegalArgumentException("Skill call missing 'skill' field");
        }

        String skill = skillCall.get("skill").asText();
        ObjectNode skillParams = skillCall.has("params") && skillCall.get("params").isObject()
            ? (ObjectNode) skillCall.get("params") : mapper.createObjectNode();
        return new SkillCall(skill, skillParams);
    }

    private record SkillCall(String skill, ObjectNode params) {}

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
