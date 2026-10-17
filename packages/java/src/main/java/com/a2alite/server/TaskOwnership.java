package com.a2alite.server;

import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.TaskAuthorizationProvider;
import org.a2aproject.sdk.server.auth.TaskOperation;

import java.util.concurrent.ConcurrentHashMap;

/** Per-server ownership, recorded by the SDK before task execution starts. */
public class TaskOwnership implements TaskAuthorizationProvider {
    private final ConcurrentHashMap<String, Owner> owners = new ConcurrentHashMap<>();

    public static final String TENANT_KEY = "a2a.lite.tenant";

    public static String principal(ServerCallContext context) {
        String tenant = (String) context.getState().getOrDefault(TENANT_KEY, "");
        String subject = context.getUser().isAuthenticated() ? context.getUser().getUsername() : "anonymous";
        String principal = context.getUser().isAuthenticated() ? subject : "a2a:anonymous";
        if (tenant.isEmpty()) return principal;
        try {
            byte[] tuple = new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsBytes(
                new String[] {"owner", tenant, principal});
            return "a2a:v1:" + java.util.Base64.getUrlEncoder().withoutPadding().encodeToString(tuple);
        } catch (java.io.IOException e) { throw new IllegalStateException(e); }
    }

    private record Owner(boolean authenticated, String key) {}
    private Owner owner(ServerCallContext context) { return new Owner(context.getUser().isAuthenticated(), principal(context)); }

    @Override
    public boolean checkRead(ServerCallContext context, String taskId, TaskOperation operation) {
        return (operation == TaskOperation.LIST_TASKS && taskId.isEmpty())
            || owner(context).equals(owners.get(taskId));
    }

    @Override
    public boolean checkWrite(ServerCallContext context, String taskId, TaskOperation operation) {
        return owner(context).equals(owners.get(taskId));
    }

    @Override
    public boolean checkCreate(ServerCallContext context, TaskOperation operation) {
        return true;
    }

    void forget(String taskId) { owners.remove(taskId); }

    @Override
    public boolean isTaskRecorded(String taskId) {
        return owners.containsKey(taskId);
    }

    @Override
    public void recordOwnership(ServerCallContext context, String taskId, TaskOperation operation) {
        owners.putIfAbsent(taskId, owner(context));
    }
}
