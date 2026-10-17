package com.a2alite.server;

import org.a2aproject.sdk.server.auth.TaskAuthorizationProvider;
import org.a2aproject.sdk.server.events.*;
import org.a2aproject.sdk.server.tasks.*;

/**
 * Coherent SDK persistence and authorization boundary. Never mix ownership from a different
 * backend. Implementations own their resources; a runtime calls close once after draining
 * execution. Durable state alone does not resume skill executions or replicate live event queues.
 */
public interface ProtocolBackend extends AutoCloseable {
    TaskStore tasks();

    TaskStateProvider taskStates();

    TaskAuthorizationProvider authorization();

    PushNotificationConfigStore pushConfigs();

    default QueueManager queues(MainEventBus bus) {
        return new InMemoryQueueManager(taskStates(), bus);
    }

    default org.a2aproject.sdk.server.agentexecution.AgentExecutor executor(
            org.a2aproject.sdk.server.agentexecution.AgentExecutor delegate) {
        return delegate;
    }

    /**
     * Optional durable snapshot subscription; caller must authorize the task through the SDK first.
     */
    default java.util.concurrent.Flow.Publisher<org.a2aproject.sdk.spec.StreamingEventKind>
            subscribe(String taskId) {
        return null;
    }

    /** Called only for a send with an existing task, before the SDK appends its message history. */
    default void prepareContinuation(
            org.a2aproject.sdk.server.ServerCallContext context, String taskId) {}

    /** Optional atomic backend cancellation; null delegates to the official local SDK handler. */
    default org.a2aproject.sdk.spec.Task cancelTask(
            org.a2aproject.sdk.server.ServerCallContext context,
            org.a2aproject.sdk.spec.CancelTaskParams params) {
        return null;
    }

    /** A Message-only execution has no durable Task and can release its ownership reservation. */
    default void messageDelivered(String taskId) {}

    default boolean durable() {
        return false;
    }

    default boolean ready() {
        return true;
    }

    /** True only when task commits atomically enqueue persistent callback deliveries. */
    default boolean durableNotifications() {
        return false;
    }

    default void start() {}

    @Override
    default void close() {}
}
