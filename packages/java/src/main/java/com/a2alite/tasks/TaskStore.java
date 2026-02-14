package com.a2alite.tasks;

import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * Interface for task persistence.
 *
 * <p>Implement this for custom backends (Redis, database, etc.).
 * Use {@link InMemoryTaskStore} for development/testing.
 */
public interface TaskStore {

    /**
     * Create a new task.
     */
    Task create(String skill, Map<String, Object> params);

    /**
     * Get a task by ID.
     */
    Optional<Task> get(String id);

    /**
     * Update a task in the store.
     */
    void update(Task task);

    /**
     * Delete a task by ID.
     *
     * @return true if the task was deleted
     */
    boolean delete(String id);

    /**
     * List tasks with optional filters.
     */
    List<Task> list(String skill, TaskState state, int limit);

    /**
     * List all tasks (up to 100).
     */
    default List<Task> list() {
        return list(null, null, 100);
    }
}
