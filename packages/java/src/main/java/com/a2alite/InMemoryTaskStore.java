package com.a2alite;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

/**
 * Thread-safe, in-memory implementation of {@link TaskStore}.
 *
 * <p>Suitable for development and testing. For production, implement
 * {@link TaskStore} with a persistent backend (e.g., Redis, database).
 *
 * <p>When {@code maxSize} is reached, the oldest task is evicted before
 * a new one is created.
 */
public class InMemoryTaskStore implements TaskStore {
    private final Map<String, Task> tasks = new ConcurrentHashMap<>();
    private final int maxSize;

    /** Creates a store with a default capacity of 10 000 tasks. */
    public InMemoryTaskStore() {
        this(10_000);
    }

    /** Creates a store with the given maximum capacity. */
    public InMemoryTaskStore(int maxSize) {
        this.maxSize = maxSize;
    }

    @Override
    public Task create(String skill, Map<String, Object> params) {
        if (tasks.size() >= maxSize) {
            tasks.entrySet().stream()
                .min(Comparator.comparing(e -> e.getValue().getCreatedAt()))
                .map(Map.Entry::getKey)
                .ifPresent(tasks::remove);
        }
        var task = new Task(
            UUID.randomUUID().toString().replace("-", ""),
            skill,
            params
        );
        tasks.put(task.getId(), task);
        return task;
    }

    @Override
    public Optional<Task> get(String taskId) {
        return Optional.ofNullable(tasks.get(taskId));
    }

    @Override
    public void update(Task task) {
        tasks.put(task.getId(), task);
    }

    @Override
    public boolean delete(String taskId) {
        return tasks.remove(taskId) != null;
    }

    @Override
    public List<Task> list(String skill, TaskState state, int limit) {
        return tasks.values().stream()
            .filter(t -> skill == null || t.getSkill().equals(skill))
            .filter(t -> state == null || t.getStatus().state() == state)
            .sorted(Comparator.comparing(Task::getCreatedAt).reversed())
            .limit(limit > 0 ? limit : 100)
            .collect(Collectors.toList());
    }

    /** Returns the current number of tasks in the store. */
    public int size() {
        return tasks.size();
    }

    /** Removes all tasks from the store. */
    public void clear() {
        tasks.clear();
    }
}
