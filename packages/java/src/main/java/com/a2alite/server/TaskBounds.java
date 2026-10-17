package com.a2alite.server;

import com.a2alite.runtime.RuntimeLimits;

import org.a2aproject.sdk.jsonrpc.common.json.JsonUtil;
import org.a2aproject.sdk.spec.Task;

import java.nio.charset.StandardCharsets;
import java.util.List;

/** Shared storage bounds; task history retains its most recent messages. */
public final class TaskBounds {
    private TaskBounds() {}

    public static Task retain(Task task, RuntimeLimits limits) {
        if (task.history() != null && task.history().size() > limits.maxHistoryLength())
            task =
                    Task.builder(task)
                            .history(
                                    List.copyOf(
                                            task.history()
                                                    .subList(
                                                            task.history().size()
                                                                    - limits.maxHistoryLength(),
                                                            task.history().size())))
                            .build();
        try {
            if (JsonUtil.toJson(task).getBytes(StandardCharsets.UTF_8).length
                    > (long) limits.maxRequestBytes() + limits.maxResultBytes() + 65536)
                throw new IllegalArgumentException("Stored task size limit exceeded");
            return task;
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalStateException("Task serialization failed", e);
        }
    }
}
