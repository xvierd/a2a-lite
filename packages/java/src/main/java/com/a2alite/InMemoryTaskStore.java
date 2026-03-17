package com.a2alite;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

public class InMemoryTaskStore implements TaskStore {
    private final Map<String, Task> tasks = new ConcurrentHashMap<>();
    private final int maxSize;

    public InMemoryTaskStore() {
        this(10000);
    }

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
            params,
            new TaskStatus(TaskState.SUBMITTED)
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
    public List<Task> list(TaskState state, String skill, int limit) {
        return tasks.values().stream()
            .filter(t -> state == null || t.getStatus().getState() == state)
            .filter(t -> skill == null || t.getSkill().equals(skill))
            .sorted(Comparator.comparing(Task::getCreatedAt).reversed())
            .limit(limit > 0 ? limit : 100)
            .collect(Collectors.toList());
    }
}
