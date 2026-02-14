package com.a2alite.tasks;

import java.time.Instant;
import java.util.*;

/**
 * Represents an A2A task.
 */
public class Task {
    private final String id;
    private final String skill;
    private final Map<String, Object> params;
    private TaskStatus status;
    private final List<TaskStatus> history;
    private final Instant createdAt;
    private Instant updatedAt;

    public Task(String id, String skill, Map<String, Object> params) {
        this.id = id;
        this.skill = skill;
        this.params = new HashMap<>(params);
        this.status = new TaskStatus(TaskState.SUBMITTED);
        this.history = new ArrayList<>();
        this.createdAt = Instant.now();
        this.updatedAt = Instant.now();
    }

    public String getId() { return id; }
    public String getSkill() { return skill; }
    public Map<String, Object> getParams() { return Collections.unmodifiableMap(params); }
    public TaskStatus getStatus() { return status; }
    public List<TaskStatus> getHistory() { return Collections.unmodifiableList(history); }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }

    /**
     * Update task status, saving current status to history.
     */
    public void updateStatus(TaskState state, String message, Double progress) {
        history.add(status);
        status = new TaskStatus(state, message, progress);
        updatedAt = Instant.now();
    }
}
