package com.a2alite.server;

import com.a2alite.runtime.RuntimeLimits;

import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.*;
import org.a2aproject.sdk.server.tasks.*;
import org.a2aproject.sdk.spec.*;

import java.time.Duration;
import java.util.*;

/** Bounded learning store. Ownership, task state and callback configuration share one lifetime. */
public final class InMemoryProtocolBackend implements ProtocolBackend {
    private final Object lock = new Object();
    private final RuntimeLimits limits;
    private org.a2aproject.sdk.server.events.InMemoryQueueManager eventQueues;
    private final LinkedHashMap<String, Long> reservations = new LinkedHashMap<>();
    private final InMemoryPushNotificationConfigStore configs =
            new InMemoryPushNotificationConfigStore();
    private final TaskOwnership authorization =
            new TaskOwnership() {
                @Override
                public void recordOwnership(
                        ServerCallContext context, String id, TaskOperation operation) {
                    synchronized (lock) {
                        if (!reservations.containsKey(id)) reserve(id);
                        super.recordOwnership(context, id, operation);
                    }
                }
            };
    private final BoundedStore tasks = new BoundedStore();

    private final class BoundedStore extends InMemoryTaskStore {
        BoundedStore() {
            super(authorization);
        }

        @Override
        public void save(Task task, boolean replicated) {
            synchronized (lock) {
                if (!authorization.isTaskRecorded(task.id())) throw new TaskNotFoundError();
                super.save(TaskBounds.retain(task, limits), replicated);
                reservations.put(task.id(), System.nanoTime());
            }
        }

        @Override
        public void delete(String id) {
            synchronized (lock) {
                remove(id);
            }
        }

        void deleteStored(String id) {
            super.delete(id);
        }
    }

    public InMemoryProtocolBackend() {
        this(RuntimeLimits.defaults());
    }

    public InMemoryProtocolBackend(RuntimeLimits limits) {
        this.limits = Objects.requireNonNull(limits);
    }

    @Override
    public org.a2aproject.sdk.server.events.QueueManager queues(
            org.a2aproject.sdk.server.events.MainEventBus bus) {
        eventQueues =
                new org.a2aproject.sdk.server.events.InMemoryQueueManager(tasks, bus) {
                    @Override
                    public org.a2aproject.sdk.server.events.EventQueue createOrTap(String id) {
                        synchronized (lock) {
                            // Reserve before the SDK creates a queue, including when storage is
                            // saturated.
                            if (!reservations.containsKey(id)) reserve(id);
                            return super.createOrTap(id);
                        }
                    }
                };
        return eventQueues;
    }

    private void reserve(String id) {
        long now = System.nanoTime();
        // Reserve before execution starts. Only finalized tasks or expired owner-only reservations
        // can leave memory; never silently evict active/input-required work to admit another call.
        var candidates = new ArrayList<String>();
        for (var entry : reservations.entrySet()) {
            Task task = tasks.get(entry.getKey());
            long age = now - entry.getValue();
            if ((task == null && age > limits.executionTimeout().plusSeconds(5).toNanos())
                    || (task != null
                            && task.status().state().isFinal()
                            && age > Duration.ofDays(1).toNanos())) candidates.add(entry.getKey());
        }
        candidates.forEach(this::remove);
        if (reservations.size() >= limits.maxStoredTasks()) {
            for (var entry : reservations.entrySet()) {
                Task task = tasks.get(entry.getKey());
                if (task != null
                        && task.status().state().isFinal()
                        && now - entry.getValue() > Duration.ofSeconds(1).toNanos()) {
                    remove(entry.getKey());
                    break;
                }
            }
        }
        if (reservations.size() >= limits.maxStoredTasks()) throw new RuntimeOverloadedException();
        reservations.put(id, now);
    }

    private void remove(String id) {
        if (eventQueues != null && eventQueues.get(id) != null) eventQueues.close(id);
        tasks.deleteStored(id);
        authorization.forget(id);
        for (var config : configs.getInfo(new ListTaskPushNotificationConfigsParams(id)).configs())
            configs.deleteInfo(id, config.id());
        reservations.remove(id);
    }

    @Override
    public void messageDelivered(String id) {
        synchronized (lock) {
            if (tasks.get(id) == null) remove(id);
        }
    }

    @Override
    public TaskStore tasks() {
        return tasks;
    }

    @Override
    public TaskStateProvider taskStates() {
        return tasks;
    }

    @Override
    public TaskAuthorizationProvider authorization() {
        return authorization;
    }

    @Override
    public PushNotificationConfigStore pushConfigs() {
        return configs;
    }

    @Override
    public void close() {
        synchronized (lock) {
            new ArrayList<>(reservations.keySet()).forEach(this::remove);
        }
    }
}
