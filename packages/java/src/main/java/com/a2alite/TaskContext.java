package com.a2alite;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Consumer;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Context passed to skills when task tracking is enabled.
 *
 * <p>Provides methods to update task status, progress, and completion state.
 * Register status-change callbacks via {@link #onStatusChange(Consumer)}.
 *
 * <pre>{@code
 * agent.skill("process", (SkillHandlerWithContext) (params, task) -> {
 *     task.update(TaskState.WORKING, "Processing...", 0.5);
 *     // ... do work ...
 *     task.complete("Done!");
 *     return "result";
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

    /** Returns the task ID. */
    public String getTaskId() {
        return task.getId();
    }

    /** Returns the current task state. */
    public TaskState getState() {
        return task.getStatus().state();
    }

    /** Returns the task parameters. */
    public Map<String, Object> getParams() {
        return task.getParams();
    }

    /** Returns the underlying {@link Task}. */
    public Task getTask() {
        return task;
    }

    /**
     * Transitions the task to a new state with an optional message and progress.
     *
     * @param state    the new state
     * @param message  optional human-readable message
     * @param progress optional progress value (0.0–1.0)
     */
    public void update(TaskState state, String message, Double progress) {
        task.updateStatus(state, message, progress);
        notifyCallbacks();
    }

    /**
     * Transitions the task to a new state using string-encoded state name.
     */
    public void update(String state, String message, Double progress) {
        update(TaskState.fromString(state), message, progress);
    }

    /**
     * Transitions the task to the given state with no message or progress.
     */
    public void update(TaskState state) {
        update(state, null, null);
    }

    /**
     * Marks the task as completed with a message.
     *
     * @param message optional completion message
     */
    public void complete(String message) {
        update(TaskState.COMPLETED, message, 1.0);
    }

    /**
     * Marks the task as completed with no message.
     */
    public void complete() {
        complete(null);
    }

    /**
     * Marks the task as failed.
     *
     * @param error description of the failure
     */
    public void fail(String error) {
        update(TaskState.FAILED, error, null);
    }

    /**
     * Registers a callback that is invoked whenever the task status changes.
     * Exceptions thrown by the callback are logged and suppressed.
     *
     * @param callback receives the new {@link TaskStatus} on every update
     */
    public void onStatusChange(Consumer<TaskStatus> callback) {
        statusCallbacks.add(callback);
    }

    private void notifyCallbacks() {
        TaskStatus newStatus = task.getStatus();
        for (var callback : statusCallbacks) {
            try {
                callback.accept(newStatus);
            } catch (Exception e) {
                LOGGER.log(Level.WARNING,
                    "Status callback error for task '" + task.getId() + "'", e);
            }
        }
    }
}
