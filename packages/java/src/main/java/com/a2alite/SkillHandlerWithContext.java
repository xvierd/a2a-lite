package com.a2alite;

import java.util.Map;

/**
 * Skill handler variant that receives a TaskContext for progress tracking.
 *
 * Example:
 * <pre>{@code
 * agent.skill("process",
 *     (SkillHandlerWithContext) (params, task) -> {
 *         task.update(TaskState.WORKING, "Starting...", 0.0);
 *         // ... do work ...
 *         task.update(TaskState.WORKING, "Almost done...", 0.9);
 *         return "result";
 *     }
 * );
 * }</pre>
 */
@FunctionalInterface
public interface SkillHandlerWithContext {
    Object handle(Map<String, Object> params, TaskContext context) throws Exception;
}
