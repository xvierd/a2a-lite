package com.a2alite.tasks;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Context passed to skills when task tracking is enabled.
 *
 * <p>Provides methods to update task status and progress.
 *
 * <pre>{@code
 * agent.skill("process", (params, task) -> {
 *     task.update(TaskState.WORKING, "Processing...", 0.5);
 *     // ... do work ...
 *     task.complete("Done!");
 *     return Map.of("success", true);
 * });
 * }</pre>
 */
public class TaskContext {
    private static final Logger LOGGER = Logger.getLogger(TaskContext.class.getName());

    private final Task task;
    private final List<Consumer<TaskStatus>> statusCallbacks = new ArrayList<>();

    public TaskContext(Task task) {
        this.task = task;
    }

    /**
     * Get the task ID.
     */
    public String getTaskId() {
        return task.getId();
    }

    /**
     * Get the current task state.
     */
    public TaskState getState() {
        return task.getStatus().state();
    }

    /**
     * Get the task parameters.
     */
    public Map<String, Object> getParams() {
        return task.getParams();
    }

    /**
     * Get the underlying task.
     */
    public Task getTask() {
        return task;
    }

    /**
     * Update task status.
     *
     * @param state   The new state
     * @param message Optional status message
     * @param progress Optional progress (0.0 to 1.0)
     */
    public void update(TaskState state, String message, Double progress) {
        task.updateStatus(state, message, progress);

        // Notify callbacks
        var newStatus = task.getStatus();
        for (var callback : statusCallbacks) {
            try {
                callback.accept(newStatus);
            } catch (Exception e) {
                LOGGER.log(Level.WARNING,
                    "Status callback error for task '" + task.getId() + "'", e);
            }
        }
    }

    /**
     * Update task status with just state and message.
     */
    public void update(TaskState state, String message) {
        update(state, message, null);
    }

    /**
     * Update task to working state.
     */
    public void update(String message, double progress) {
        update(TaskState.WORKING, message, progress);
    }

    /**
     * Mark task as completed.
     */
    public void complete(String message) {
        update(TaskState.COMPLETED, message, 1.0);
    }

    /**
     * Mark task as completed with no message.
     */
    public void complete() {
        complete(null);
    }

    /**
     * Mark task as failed.
     */
    public void fail(String error) {
        update(TaskState.FAILED, error, null);
    }

    /**
     * Register a status change callback.
     */
    public void onStatusChange(Consumer<TaskStatus> callback) {
        statusCallbacks.add(callback);
    }
}
