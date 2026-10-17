package com.a2alite.server;

import org.a2aproject.sdk.spec.*;

import java.util.concurrent.Flow;
import java.util.concurrent.atomic.*;
import java.util.function.Function;

/** Reconcile queued local events rejected after another replica committed a terminal state. */
final class CanonicalTaskStream implements Flow.Publisher<StreamingEventKind> {
    private final Flow.Publisher<StreamingEventKind> source;
    private final Function<String, Task> authorizedTask;
    private final java.util.function.Consumer<String> messageDelivered;

    CanonicalTaskStream(
            Flow.Publisher<StreamingEventKind> source, Function<String, Task> authorizedTask) {
        this(source, authorizedTask, id -> {});
    }

    CanonicalTaskStream(
            Flow.Publisher<StreamingEventKind> source,
            Function<String, Task> authorizedTask,
            java.util.function.Consumer<String> messageDelivered) {
        this.source = source;
        this.authorizedTask = authorizedTask;
        this.messageDelivered = messageDelivered;
    }

    @Override
    public void subscribe(Flow.Subscriber<? super StreamingEventKind> downstream) {
        source.subscribe(
                new Flow.Subscriber<>() {
                    private String taskId;
                    private boolean terminal;
                    private final AtomicLong demand = new AtomicLong();
                    private final AtomicBoolean canceled = new AtomicBoolean();

                    @Override
                    public void onSubscribe(Flow.Subscription upstream) {
                        downstream.onSubscribe(
                                new Flow.Subscription() {
                                    @Override
                                    public void request(long n) {
                                        if (n > 0)
                                            demand.getAndUpdate(
                                                    value ->
                                                            value > Long.MAX_VALUE - n
                                                                    ? Long.MAX_VALUE
                                                                    : value + n);
                                        upstream.request(n);
                                    }

                                    @Override
                                    public void cancel() {
                                        canceled.set(true);
                                        upstream.cancel();
                                    }
                                });
                    }

                    @Override
                    public void onNext(StreamingEventKind event) {
                        if (event instanceof Task task) {
                            taskId = task.id();
                            terminal = task.status().state().isFinal();
                        } else if (event instanceof TaskStatusUpdateEvent status) {
                            taskId = status.taskId();
                            terminal = status.status().state().isFinal();
                        } else if (event instanceof TaskArtifactUpdateEvent artifact)
                            taskId = artifact.taskId();
                        demand.getAndUpdate(
                                value -> value == Long.MAX_VALUE ? value : Math.max(0, value - 1));
                        downstream.onNext(event);
                        if (event instanceof Message message && message.taskId() != null) {
                            try {
                                messageDelivered.accept(message.taskId());
                            } catch (RuntimeException ignored) {
                                /* Expired-reservation reconciliation retries cleanup. */
                            }
                        }
                    }

                    @Override
                    public void onError(Throwable error) {
                        if (canceled.get()) return;
                        Task canonical = null;
                        if (taskId != null && demand.get() > 0) {
                            try {
                                canonical = authorizedTask.apply(taskId);
                            } catch (RuntimeException ignored) {
                                /* Authorization/storage errors stay failures. */
                            }
                        }
                        if (canonical != null && canonical.status().state().isFinal()) {
                            downstream.onNext(
                                    new TaskStatusUpdateEvent(
                                            canonical.id(),
                                            canonical.status(),
                                            canonical.contextId(),
                                            canonical.metadata()));
                            downstream.onComplete();
                        } else downstream.onError(error);
                    }

                    @Override
                    public void onComplete() {
                        if (canceled.get()) return;
                        if (!terminal && taskId != null && demand.get() > 0) {
                            try {
                                Task canonical = authorizedTask.apply(taskId);
                                if (canonical != null && canonical.status().state().isFinal())
                                    downstream.onNext(
                                            new TaskStatusUpdateEvent(
                                                    canonical.id(),
                                                    canonical.status(),
                                                    canonical.contextId(),
                                                    canonical.metadata()));
                            } catch (RuntimeException ignored) {
                                /* Keep the existing completion when storage is unavailable. */
                            }
                        }
                        downstream.onComplete();
                    }
                });
    }
}
