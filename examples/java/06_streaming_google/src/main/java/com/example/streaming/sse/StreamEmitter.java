package com.example.streaming.sse;

/**
 * Stream Emitter - sink for skill output.
 *
 * Skills write their incremental output through this interface, independent of
 * the transport. Two implementations exist:
 * - {@link SseEventEmitter}: emits A2A v1.0 SSE events (task / statusUpdate /
 *   artifactUpdate) on a SendStreamingMessage response.
 * - {@link CollectingEmitter}: buffers the output for a synchronous SendMessage
 *   response.
 */
public interface StreamEmitter {

    /**
     * Report a working-status update (v1.0: statusUpdate with TASK_STATE_WORKING).
     */
    void sendStatus(String message);

    /**
     * Report numeric progress (v1.0: statusUpdate with TASK_STATE_WORKING).
     */
    void sendProgress(int current, int total, String message);

    /**
     * Emit a chunk of the result artifact (v1.0: artifactUpdate, append=true).
     */
    void sendText(String chunk);

    /**
     * Report a failure (v1.0: statusUpdate with TASK_STATE_FAILED).
     */
    void sendError(String errorMessage);

    /**
     * Mark the task as completed (v1.0: statusUpdate with TASK_STATE_COMPLETED).
     */
    void complete(String message);

    /**
     * Check whether the stream can still accept events.
     */
    boolean isClosed();
}
