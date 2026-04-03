package com.a2alite.push;

import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Server-side registry mapping task IDs to per-task webhook configurations.
 *
 * <p>When a caller sends a {@code tasks/pushNotification/set} JSON-RPC request,
 * the server stores the webhook URL (and optional bearer token) here. On task
 * completion the executor consults this registry and fires the webhook if one
 * is registered for the finishing task.
 *
 * <p>Thread-safe: backed by a {@link ConcurrentHashMap}.
 */
public class TaskPushRegistry {

    /**
     * Webhook configuration for a single task.
     *
     * @param url   the webhook endpoint URL
     * @param token optional bearer token sent in the {@code Authorization} header,
     *              or {@code null} if no authentication is required
     */
    public record PushConfig(String url, String token) {}

    private final ConcurrentHashMap<String, PushConfig> configs = new ConcurrentHashMap<>();

    /**
     * Register (or replace) a push notification webhook for the given task.
     *
     * @param taskId the task ID
     * @param url    the webhook URL
     * @param token  optional bearer token, or {@code null}
     */
    public void set(String taskId, String url, String token) {
        configs.put(taskId, new PushConfig(url, token));
    }

    /**
     * Register a push notification webhook without a bearer token.
     */
    public void set(String taskId, String url) {
        set(taskId, url, null);
    }

    /**
     * Retrieve the push config for the given task, if any.
     */
    public Optional<PushConfig> get(String taskId) {
        return Optional.ofNullable(configs.get(taskId));
    }

    /**
     * Remove the push config for the given task.
     *
     * @return {@code true} if a config was removed, {@code false} if none existed
     */
    public boolean delete(String taskId) {
        return configs.remove(taskId) != null;
    }

    /**
     * Check whether a push config is registered for the given task.
     */
    public boolean contains(String taskId) {
        return configs.containsKey(taskId);
    }
}
