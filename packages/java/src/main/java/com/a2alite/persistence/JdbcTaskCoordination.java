package com.a2alite.persistence;

import com.a2alite.LiteAgentExecutor;

import org.a2aproject.sdk.server.agentexecution.*;
import org.a2aproject.sdk.server.tasks.AgentEmitter;
import org.a2aproject.sdk.spec.*;

import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

/**
 * Prototype multi-replica status stream and cancellation relay. Persisted per-task revisions avoid
 * gaps caused by global sequence allocation before another transaction commits. Existing
 * subscribers receive subsequent status snapshots; arbitrary functions are not resumed.
 */
final class JdbcTaskCoordination implements AutoCloseable {
    private final JdbcProtocolBackend backend;
    private final ConcurrentMap<String, LiteAgentExecutor> executing = new ConcurrentHashMap<>();
    private final Set<Subscription> subscriptions = ConcurrentHashMap.newKeySet();
    private final Semaphore permits;
    private final ScheduledExecutorService monitor =
            Executors.newSingleThreadScheduledExecutor(
                    r -> {
                        var t = new Thread(r, "a2a-lite-cancel-relay");
                        t.setDaemon(true);
                        return t;
                    });
    private final AtomicBoolean started = new AtomicBoolean(), closed = new AtomicBoolean();

    JdbcTaskCoordination(JdbcProtocolBackend backend, int maxStreams) {
        this.backend = backend;
        permits = new Semaphore(maxStreams);
    }

    AgentExecutor executor(AgentExecutor delegate) {
        if (!(delegate instanceof LiteAgentExecutor lite))
            throw new IllegalArgumentException("JDBC coordination requires the Lite executor");
        return new AgentExecutor() {
            @Override
            public void execute(RequestContext context, AgentEmitter emitter) {
                if (executing.putIfAbsent(context.getTaskId(), lite) != null)
                    throw new org.a2aproject.sdk.spec.InternalError("Task is already executing");
                try {
                    backend.executions.claim(context.getTaskId());
                    delegate.execute(context, emitter);
                } finally {
                    executing.remove(context.getTaskId(), lite);
                }
            }

            @Override
            public void cancel(RequestContext context, AgentEmitter emitter) {
                delegate.cancel(context, emitter);
            }
        };
    }

    void messageDelivered(String id) {
        executing.remove(id);
    }

    void start() {
        if (started.compareAndSet(false, true))
            monitor.scheduleWithFixedDelay(this::relayCancellation, 50, 50, TimeUnit.MILLISECONDS);
    }

    private long nextHeartbeat;

    private void relayCancellation() {
        boolean heartbeat = System.nanoTime() >= nextHeartbeat;
        if (heartbeat)
            nextHeartbeat =
                    System.nanoTime() + java.util.concurrent.TimeUnit.MILLISECONDS.toNanos(500);
        executing.forEach(
                (id, executor) -> {
                    try {
                        Task task = backend.get(id);
                        if (task != null
                                && (task.status().state() == TaskState.TASK_STATE_CANCELED
                                        || task.status().state() == TaskState.TASK_STATE_FAILED))
                            executor.interruptExecution(id);
                        else if (heartbeat && !backend.executions.renew(id))
                            executor.interruptExecution(id);
                    } catch (RuntimeException ignored) {
                        /* Leave durable state untouched; readiness reports database failure. */
                    }
                });
        if (heartbeat)
            try {
                backend.executions.reconcileExpired();
            } catch (RuntimeException ignored) {
                /* Readiness fails closed. */
            }
    }

    Flow.Publisher<StreamingEventKind> subscribe(String taskId) {
        return subscriber -> {
            Objects.requireNonNull(subscriber);
            if (closed.get() || !permits.tryAcquire()) {
                subscriber.onSubscribe(
                        new Flow.Subscription() {
                            public void request(long n) {}

                            public void cancel() {}
                        });
                subscriber.onError(
                        new org.a2aproject.sdk.spec.InternalError(
                                "Subscription capacity unavailable"));
                return;
            }
            var subscription = new Subscription(taskId, subscriber);
            subscriptions.add(subscription);
            subscriber.onSubscribe(subscription);
            subscription.thread.start();
        };
    }

    private record Revision(long number, Task task) {}

    private final class Subscription implements Flow.Subscription, Runnable {
        private final String id;
        private final Flow.Subscriber<? super StreamingEventKind> subscriber;
        private final AtomicLong demand = new AtomicLong();
        private final AtomicBoolean canceled = new AtomicBoolean();
        private final Thread thread;

        Subscription(String id, Flow.Subscriber<? super StreamingEventKind> subscriber) {
            this.id = id;
            this.subscriber = subscriber;
            thread = new Thread(this, "a2a-lite-snapshot-stream");
            thread.setDaemon(true);
        }

        @Override
        public void request(long n) {
            if (n <= 0) {
                cancel();
                subscriber.onError(new IllegalArgumentException("Positive stream demand required"));
                return;
            }
            demand.getAndUpdate(
                    current -> current > Long.MAX_VALUE - n ? Long.MAX_VALUE : current + n);
        }

        @Override
        public void cancel() {
            canceled.set(true);
            thread.interrupt();
        }

        private void emit(StreamingEventKind event) throws InterruptedException {
            while (demand.get() == 0 && !canceled.get()) Thread.sleep(5);
            if (canceled.get()) throw new InterruptedException();
            demand.getAndUpdate(value -> value == Long.MAX_VALUE ? value : value - 1);
            subscriber.onNext(event);
        }

        @Override
        public void run() {
            try {
                Revision initial =
                        backend.transaction(
                                c -> {
                                    try (var s =
                                            c.prepareStatement(
                                                    "SELECT revision,payload FROM a2a_lite_tasks"
                                                            + " WHERE task_id=?")) {
                                        s.setString(1, id);
                                        try (var row = s.executeQuery()) {
                                            return row.next()
                                                    ? new Revision(
                                                            row.getLong(1),
                                                            JdbcProtocolBackend.decode(
                                                                    row.getString(2), Task.class))
                                                    : null;
                                        }
                                    }
                                });
                if (initial == null) throw new TaskNotFoundError();
                emit(initial.task());
                long revision = initial.number();
                var artifacts = new HashMap<String, Artifact>();
                if (initial.task().artifacts() != null)
                    initial.task()
                            .artifacts()
                            .forEach(artifact -> artifacts.put(artifact.artifactId(), artifact));
                if ((initial.task().status().state().isFinal()
                        || initial.task().status().state().isInterrupted())) {
                    subscriber.onComplete();
                    return;
                }
                while (!canceled.get() && !closed.get()) {
                    final long after = revision;
                    var updates =
                            backend.transaction(
                                    c -> {
                                        var rows = new ArrayList<Revision>();
                                        try (var s =
                                                c.prepareStatement(
                                                        "SELECT revision,payload FROM"
                                                            + " a2a_lite_events WHERE task_id=? AND"
                                                            + " revision>? ORDER BY revision LIMIT"
                                                            + " 64")) {
                                            s.setString(1, id);
                                            s.setLong(2, after);
                                            try (var result = s.executeQuery()) {
                                                while (result.next())
                                                    rows.add(
                                                            new Revision(
                                                                    result.getLong(1),
                                                                    JdbcProtocolBackend.decode(
                                                                            result.getString(2),
                                                                            Task.class)));
                                            }
                                        }
                                        return rows;
                                    });
                    for (var next : updates) {
                        var task = next.task();
                        if (task.artifacts() != null)
                            for (var artifact : task.artifacts()) {
                                if (!artifact.equals(
                                        artifacts.put(artifact.artifactId(), artifact)))
                                    emit(
                                            new TaskArtifactUpdateEvent(
                                                    id,
                                                    artifact,
                                                    task.contextId(),
                                                    false,
                                                    true,
                                                    null));
                            }
                        emit(
                                new TaskStatusUpdateEvent(
                                        id, task.status(), task.contextId(), task.metadata()));
                        revision = next.number();
                        if ((task.status().state().isFinal()
                                || task.status().state().isInterrupted())) {
                            subscriber.onComplete();
                            return;
                        }
                    }
                    Thread.sleep(50);
                }
            } catch (InterruptedException ignored) {
                Thread.currentThread().interrupt();
            } catch (Throwable error) {
                if (!canceled.get())
                    subscriber.onError(
                            new org.a2aproject.sdk.spec.InternalError(
                                    "Durable subscription failed"));
            } finally {
                subscriptions.remove(this);
                permits.release();
            }
        }
    }

    @Override
    public void close() {
        if (!closed.compareAndSet(false, true)) return;
        monitor.shutdownNow();
        subscriptions.forEach(Subscription::cancel);
    }
}
