package com.example.streaming.sse;

import io.javalin.http.Context;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.io.IOException;
import java.io.PrintWriter;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Server-Sent Events (SSE) Event Emitter
 * 
 * Manages SSE connections for streaming responses.
 * Required infrastructure for Google A2A SDK streaming.
 */
public class SseEventEmitter {
    
    private static final ObjectMapper mapper = new ObjectMapper();
    private final Context ctx;
    private final PrintWriter writer;
    private final AtomicBoolean closed = new AtomicBoolean(false);
    
    public SseEventEmitter(Context ctx) {
        this.ctx = ctx;
        try {
            this.writer = ctx.res().getWriter();
        } catch (IOException e) {
            throw new RuntimeException("Failed to get response writer", e);
        }
    }
    
    /**
     * Send an SSE event with the given name and data.
     */
    public void sendEvent(String eventName, Object data) {
        if (closed.get()) {
            return;
        }
        
        try {
            String jsonData = mapper.writeValueAsString(data);
            writer.write("event: " + eventName + "\n");
            writer.write("data: " + jsonData + "\n\n");
            writer.flush();
        } catch (IOException e) {
            System.err.println("[SSE] Failed to send event: " + e.getMessage());
            closed.set(true);
        }
    }
    
    /**
     * Send a data chunk for streaming content.
     */
    public void sendChunk(String chunk) {
        if (closed.get()) {
            return;
        }
        
        try {
            ObjectNode data = mapper.createObjectNode();
            data.put("type", "chunk");
            data.put("content", chunk);
            data.put("timestamp", System.currentTimeMillis());
            
            writer.write("event: chunk\n");
            writer.write("data: " + mapper.writeValueAsString(data) + "\n\n");
            writer.flush();
        } catch (IOException e) {
            System.err.println("[SSE] Failed to send chunk: " + e.getMessage());
            closed.set(true);
        }
    }
    
    /**
     * Send a progress update.
     */
    public void sendProgress(int current, int total, String message) {
        if (closed.get()) {
            return;
        }
        
        try {
            ObjectNode data = mapper.createObjectNode();
            data.put("type", "progress");
            data.put("current", current);
            data.put("total", total);
            data.put("percent", (int) ((current * 100.0) / total));
            data.put("message", message);
            
            writer.write("event: progress\n");
            writer.write("data: " + mapper.writeValueAsString(data) + "\n\n");
            writer.flush();
        } catch (IOException e) {
            System.err.println("[SSE] Failed to send progress: " + e.getMessage());
            closed.set(true);
        }
    }
    
    /**
     * Send a token/word for word-by-word streaming.
     */
    public void sendToken(String token, int index, boolean isLast) {
        if (closed.get()) {
            return;
        }
        
        try {
            ObjectNode data = mapper.createObjectNode();
            data.put("type", "token");
            data.put("token", token);
            data.put("index", index);
            data.put("isLast", isLast);
            
            writer.write("event: token\n");
            writer.write("data: " + mapper.writeValueAsString(data) + "\n\n");
            writer.flush();
        } catch (IOException e) {
            System.err.println("[SSE] Failed to send token: " + e.getMessage());
            closed.set(true);
        }
    }
    
    /**
     * Send an error event.
     */
    public void sendError(String errorMessage) {
        if (closed.get()) {
            return;
        }
        
        try {
            ObjectNode data = mapper.createObjectNode();
            data.put("type", "error");
            data.put("error", errorMessage);
            data.put("timestamp", System.currentTimeMillis());
            
            writer.write("event: error\n");
            writer.write("data: " + mapper.writeValueAsString(data) + "\n\n");
            writer.flush();
        } catch (IOException e) {
            System.err.println("[SSE] Failed to send error: " + e.getMessage());
        }
    }
    
    /**
     * Complete the stream.
     */
    public void complete() {
        if (closed.compareAndSet(false, true)) {
            try {
                ObjectNode data = mapper.createObjectNode();
                data.put("type", "complete");
                data.put("timestamp", System.currentTimeMillis());
                
                writer.write("event: complete\n");
                writer.write("data: " + mapper.writeValueAsString(data) + "\n\n");
                writer.flush();
            } catch (IOException e) {
                System.err.println("[SSE] Failed to complete: " + e.getMessage());
            }
        }
    }
    
    /**
     * Check if the connection is closed.
     */
    public boolean isClosed() {
        return closed.get() || writer.checkError();
    }
    
    /**
     * Close the connection.
     */
    public void close() {
        closed.set(true);
        try {
            writer.close();
        } catch (Exception e) {
            // Ignore
        }
    }
}
