package com.a2alite;

import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

public class TaskStatus {
    private final TaskState state;
    private final String message;
    private final Double progress;
    private final Instant timestamp;

    public TaskStatus(TaskState state, String message, Double progress) {
        this.state = state;
        this.message = message;
        this.progress = progress;
        this.timestamp = Instant.now();
    }

    public TaskStatus(TaskState state) {
        this(state, null, null);
    }

    public TaskState getState() { return state; }
    public String getMessage() { return message; }
    public Double getProgress() { return progress; }
    public Instant getTimestamp() { return timestamp; }

    public Map<String, Object> toDict() {
        var map = new HashMap<String, Object>();
        map.put("state", state.getValue());
        map.put("message", message);
        map.put("progress", progress);
        map.put("timestamp", timestamp.toString());
        return map;
    }
}
