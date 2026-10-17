package com.a2alite.server;

import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.TaskAuthorizationProvider;
import org.a2aproject.sdk.server.auth.TaskOperation;

import java.util.concurrent.ConcurrentHashMap;

/** Per-server ownership, recorded by the SDK before task execution starts. */
final class TaskOwnership implements TaskAuthorizationProvider {
    private final ConcurrentHashMap<String, String> owners = new ConcurrentHashMap<>();

    private String principal(ServerCallContext context) {
        return context.getUser().isAuthenticated()
            ? "user:" + context.getUser().getUsername() : "anonymous";
    }

    @Override
    public boolean checkRead(ServerCallContext context, String taskId, TaskOperation operation) {
        return (operation == TaskOperation.LIST_TASKS && taskId.isEmpty())
            || principal(context).equals(owners.get(taskId));
    }

    @Override
    public boolean checkWrite(ServerCallContext context, String taskId, TaskOperation operation) {
        return principal(context).equals(owners.get(taskId));
    }

    @Override
    public boolean checkCreate(ServerCallContext context, TaskOperation operation) {
        return true;
    }

    @Override
    public boolean isTaskRecorded(String taskId) {
        return owners.containsKey(taskId);
    }

    @Override
    public void recordOwnership(ServerCallContext context, String taskId, TaskOperation operation) {
        owners.putIfAbsent(taskId, principal(context));
    }
}
