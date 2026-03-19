package com.a2alite;

import java.time.Instant;
import java.util.Map;
import java.util.Optional;

/**
 * Immutable snapshot of a task's status at a point in time.
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

    /** Returns the status message, if present. */
    public Optional<String> getMessage() {
        return Optional.ofNullable(message);
    }

    /** Returns the progress value (0.0–1.0), if present. */
    public Optional<Double> getProgress() {
        return Optional.ofNullable(progress);
    }

    /**
     * Convert to a plain map representation.
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
