package com.a2alite;

import java.util.List;
import java.util.Map;
import java.util.Optional;

public interface TaskStore {
    Task create(String skill, Map<String, Object> params);
    Optional<Task> get(String taskId);
    void update(Task task);
    boolean delete(String taskId);
    List<Task> list(TaskState state, String skill, int limit);
}
