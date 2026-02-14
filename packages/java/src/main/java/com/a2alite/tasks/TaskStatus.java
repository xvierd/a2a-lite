package com.a2alite.tasks;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;

/**
 * Current status of a task.
 */
public record TaskStatus(
    TaskState state,
    String message,
    Double progress,
    Instant timestamp
) {
    public TaskStatus(TaskState state) {
        this(state, null, null, Instant.now());
    }

    public TaskStatus(TaskState state, String message) {
        this(state, message, null, Instant.now());
    }

    public TaskStatus(TaskState state, String message, Double progress) {
        this(state, message, progress, Instant.now());
    }

    public Optional<String> getMessage() {
        return Optional.ofNullable(message);
    }

    public Optional<Double> getProgress() {
        return Optional.ofNullable(progress);
    }

    /**
     * Convert to a map representation.
     */
    public Map<String, Object> toMap() {
        return Map.of(
            "state", state.getValue(),
            "message", message != null ? message : "",
            "progress", progress != null ? progress : 0.0,
            "timestamp", timestamp.toString()
        );
    }
}
