package com.example.streaming.sse;

/**
 * Collecting Emitter - buffers skill output for synchronous SendMessage calls.
 *
 * Runs the same streaming skills without SSE: text chunks are accumulated and
 * the terminal status (completed / failed) decides the final response text.
 */
public class CollectingEmitter implements StreamEmitter {

    private final StringBuilder text = new StringBuilder();
    private String finalMessage;
    private String error;

    @Override
    public void sendStatus(String message) {
        // Intermediate working updates are not part of the sync response
    }

    @Override
    public void sendProgress(int current, int total, String message) {
        // Intermediate progress updates are not part of the sync response
    }

    @Override
    public void sendText(String chunk) {
        text.append(chunk);
    }

    @Override
    public void sendError(String errorMessage) {
        this.error = errorMessage;
    }

    @Override
    public void complete(String message) {
        this.finalMessage = message;
    }

    @Override
    public boolean isClosed() {
        return false;
    }

    /**
     * The text to return in the SendMessage response.
     */
    public String getResult() {
        if (error != null) {
            return "Error: " + error;
        }
        if (finalMessage != null) {
            return finalMessage;
        }
        return text.toString().trim();
    }
}
