package com.a2alite;

/**
 * Context passed to skills when task tracking is enabled.
 *
 * Skills request a TaskContext by using SkillHandlerWithContext,
 * which is detected and injected by the executor.
 *
 * Example:
 * <pre>{@code
 * agent.skill("process", (SkillHandlerWithContext) (params, task) -> {
 *     task.update(TaskState.WORKING, "Processing...", 0.5);
 *     return "done";
 * });
 * }</pre>
 */
public class TaskContext {
    private final Task task;

    public TaskContext(Task task) {
        this.task = task;
    }

    public String getTaskId() {
        return task.getId();
    }

    public TaskState getState() {
        return task.getStatus().getState();
    }

    public void update(TaskState state, String message, Double progress) {
        task.updateStatus(state, message, progress);
    }

    public void update(String state, String message, Double progress) {
        update(TaskState.fromValue(state), message, progress);
    }

    public void update(TaskState state) {
        update(state, null, null);
    }

    public Task getTask() {
        return task;
    }
}
