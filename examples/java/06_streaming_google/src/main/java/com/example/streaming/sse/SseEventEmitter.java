package com.example.streaming.sse;

import io.javalin.http.Context;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.io.PrintWriter;
import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Server-Sent Events (SSE) Event Emitter - A2A protocol v1.0 wire format.
 *
 * Emits v1.0 streaming events as `data: {...}` lines on the SendStreamingMessage
 * HTTP response. Event payloads are wrapped as JSON-RPC results with one of the
 * v1.0 keys: `task` (always the first event), `statusUpdate` or `artifactUpdate`.
 * There is no `final` field — closing the stream signals terminality.
 */
public class SseEventEmitter implements StreamEmitter {

    private static final ObjectMapper mapper = new ObjectMapper();

    private final PrintWriter writer;
    private final String taskId;
    private final String contextId;
    private final String artifactId = UUID.randomUUID().toString();
    private final AtomicBoolean closed = new AtomicBoolean(false);

    public SseEventEmitter(Context ctx, String taskId, String contextId) {
        this.taskId = taskId;
        this.contextId = contextId;
        try {
            this.writer = ctx.res().getWriter();
        } catch (IOException e) {
            throw new RuntimeException("Failed to get response writer", e);
        }
    }

    /**
     * Send the initial Task event. v1.0 requires the task to be the first
     * event of the stream.
     */
    public void sendTask() {
        ObjectNode task = mapper.createObjectNode();
        task.put("id", taskId);
        task.put("contextId", contextId);
        task.set("status", createStatus("TASK_STATE_SUBMITTED", null));
        task.set("artifacts", mapper.createArrayNode());
        send("task", task);
    }

    @Override
    public void sendStatus(String message) {
        sendStatusUpdate("TASK_STATE_WORKING", message);
    }

    @Override
    public void sendProgress(int current, int total, String message) {
        int percent = total > 0 ? (int) ((current * 100.0) / total) : 0;
        sendStatusUpdate("TASK_STATE_WORKING",
            message + " (" + current + "/" + total + ", " + percent + "%)");
    }

    @Override
    public void sendText(String chunk) {
        ObjectNode artifact = mapper.createObjectNode();
        artifact.put("artifactId", artifactId);
        artifact.put("name", "response");
        ArrayNode parts = mapper.createArrayNode();
        ObjectNode textPart = mapper.createObjectNode();
        textPart.put("text", chunk);
        parts.add(textPart);
        artifact.set("parts", parts);

        ObjectNode update = mapper.createObjectNode();
        update.put("taskId", taskId);
        update.set("artifact", artifact);
        update.put("append", true);
        update.put("lastChunk", false);
        send("artifactUpdate", update);
    }

    @Override
    public void sendError(String errorMessage) {
        sendStatusUpdate("TASK_STATE_FAILED", errorMessage);
        closed.set(true);
    }

    @Override
    public void complete(String message) {
        sendStatusUpdate("TASK_STATE_COMPLETED", message);
        closed.set(true);
    }

    @Override
    public boolean isClosed() {
        return closed.get() || writer.checkError();
    }

    /**
     * Emit a v1.0 statusUpdate event: {"taskId","contextId","status":{...}}.
     */
    private void sendStatusUpdate(String state, String message) {
        ObjectNode update = mapper.createObjectNode();
        update.put("taskId", taskId);
        update.put("contextId", contextId);
        update.set("status", createStatus(state, message));
        send("statusUpdate", update);
    }

    /**
     * Build a v1.0 TaskStatus: {"state":"TASK_STATE_*","timestamp":...,"message":{...}}.
     */
    private ObjectNode createStatus(String state, String message) {
        ObjectNode status = mapper.createObjectNode();
        status.put("state", state);
        status.put("timestamp", Instant.now().toString());
        if (message != null) {
            status.set("message", createAgentMessage(message));
        }
        return status;
    }

    /**
     * Build a v1.0 agent Message: every message carries a messageId and the
     * uppercase ROLE_AGENT role; text parts are {"text": ...} with no kind/type.
     */
    private ObjectNode createAgentMessage(String text) {
        ObjectNode message = mapper.createObjectNode();
        message.put("messageId", UUID.randomUUID().toString());
        message.put("role", "ROLE_AGENT");
        ArrayNode parts = mapper.createArrayNode();
        ObjectNode textPart = mapper.createObjectNode();
        textPart.put("text", text);
        parts.add(textPart);
        message.set("parts", parts);
        return message;
    }

    /**
     * Write one SSE event: data: {"result":{"<key>":<payload>}}.
     */
    private void send(String key, ObjectNode payload) {
        if (closed.get()) {
            return;
        }
        try {
            ObjectNode result = mapper.createObjectNode();
            result.set(key, payload);
            ObjectNode envelope = mapper.createObjectNode();
            envelope.set("result", result);

            writer.write("data: " + mapper.writeValueAsString(envelope) + "\n\n");
            writer.flush();
        } catch (IOException e) {
            System.err.println("[SSE] Failed to send event: " + e.getMessage());
            closed.set(true);
        }
    }
}
