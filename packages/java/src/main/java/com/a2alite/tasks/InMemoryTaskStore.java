package com.a2alite.tasks;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * Thread-safe in-memory task store.
 *
 * <p>Suitable for development and testing. For production, implement
 * {@link TaskStore} with a persistent backend.
 */
public class InMemoryTaskStore implements TaskStore {
    private final Map<String, Task> tasks = new ConcurrentHashMap<>();

    @Override
    public Task create(String skill, Map<String, Object> params) {
        String id = UUID.randomUUID().toString().replace("-", "");
        var task = new Task(id, skill, params);
        tasks.put(id, task);
        return task;
    }

    @Override
    public Optional<Task> get(String id) {
        return Optional.ofNullable(tasks.get(id));
    }

    @Override
    public void update(Task task) {
        tasks.put(task.getId(), task);
    }

    @Override
    public boolean delete(String id) {
        return tasks.remove(id) != null;
    }

    @Override
    public List<Task> list(String skill, TaskState state, int limit) {
        return tasks.values().stream()
            .filter(t -> skill == null || t.getSkill().equals(skill))
            .filter(t -> state == null || t.getStatus().state() == state)
            .sorted(Comparator.comparing(Task::getCreatedAt).reversed())
            .limit(limit)
            .collect(Collectors.toList());
    }

    /**
     * Get the number of tasks in the store.
     */
    public int size() {
        return tasks.size();
    }

    /**
     * Clear all tasks.
     */
    public void clear() {
        tasks.clear();
    }
}
