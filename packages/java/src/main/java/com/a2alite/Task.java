package com.a2alite;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class Task {
    private final String id;
    private final String skill;
    private final Map<String, Object> params;
    private TaskStatus status;
    private Object result;
    private String error;
    private final List<Object> artifacts = new ArrayList<>();
    private final List<TaskStatus> history = new ArrayList<>();
    private final Instant createdAt;
    private Instant updatedAt;

    public Task(String id, String skill, Map<String, Object> params, TaskStatus status) {
        this.id = id;
        this.skill = skill;
        this.params = params;
        this.status = status;
        this.createdAt = Instant.now();
        this.updatedAt = createdAt;
    }

    public void updateStatus(TaskState state, String message, Double progress) {
        history.add(status);
        status = new TaskStatus(state, message, progress);
        updatedAt = Instant.now();
    }

    public String getId() { return id; }
    public String getSkill() { return skill; }
    public Map<String, Object> getParams() { return params; }
    public TaskStatus getStatus() { return status; }
    public Object getResult() { return result; }
    public void setResult(Object result) { this.result = result; }
    public String getError() { return error; }
    public void setError(String error) { this.error = error; }
    public List<TaskStatus> getHistory() { return history; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getUpdatedAt() { return updatedAt; }
}
