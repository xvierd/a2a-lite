package com.a2alite;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Persistence contract for A2A tasks.
 *
 * <p>Use {@link InMemoryTaskStore} for development and testing.
 * Implement this interface for production backends (e.g., Redis, database).
 */
public interface TaskStore {

    /** Creates a new task with the given skill name and parameters. */
    Task create(String skill, Map<String, Object> params);

    /** Returns the task with the given ID, or empty if not found. */
    Optional<Task> get(String taskId);

    /** Persists an updated task. */
    void update(Task task);

    /**
     * Deletes the task with the given ID.
     *
     * @return {@code true} if the task existed and was deleted
     */
    boolean delete(String taskId);

    /**
     * Lists tasks with optional filters.
     *
     * @param skill the skill name to filter by, or {@code null} for all
     * @param state the state to filter by, or {@code null} for all
     * @param limit maximum number of results to return
     */
    List<Task> list(String skill, TaskState state, int limit);

    /** Lists all tasks (up to 100). */
    default List<Task> list() {
        return list(null, null, 100);
    }
}
