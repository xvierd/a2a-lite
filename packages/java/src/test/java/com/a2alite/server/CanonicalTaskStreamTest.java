package com.a2alite.server;

import static org.assertj.core.api.Assertions.*;

import org.a2aproject.sdk.spec.*;
import org.junit.jupiter.api.Test;

import java.util.*;
import java.util.concurrent.Flow;
import java.util.concurrent.atomic.*;

class CanonicalTaskStreamTest {
    @Test
    void queuedPreCancellationEventFailureReplaysAuthorizedTerminalWithoutWritingStaleState() {
        var working =
                Task.builder()
                        .id("task")
                        .contextId("ctx")
                        .status(new TaskStatus(TaskState.TASK_STATE_WORKING))
                        .build();
        var durable = new AtomicReference<>(working);
        var staleWrites = new AtomicInteger();
        Flow.Publisher<StreamingEventKind> queued =
                subscriber ->
                        subscriber.onSubscribe(
                                new Flow.Subscription() {
                                    boolean started;

                                    @Override
                                    public void request(long n) {
                                        if (started) return;
                                        started = true;
                                        subscriber.onNext(working);
                                        // Replica B commits CANCELED before A consumes its already
                                        // queued WORKING event.
                                        durable.set(
                                                Task.builder(working)
                                                        .status(
                                                                new TaskStatus(
                                                                        TaskState
                                                                                .TASK_STATE_CANCELED))
                                                        .build());
                                        staleWrites.incrementAndGet();
                                        subscriber.onError(
                                                new org.a2aproject.sdk.spec.InternalError(
                                                        "TaskStore persistence failed: Stale task"
                                                            + " writer"));
                                    }

                                    @Override
                                    public void cancel() {}
                                });
        var events = new ArrayList<StreamingEventKind>();
        var done = new AtomicBoolean();
        new CanonicalTaskStream(
                        queued,
                        id -> {
                            assertThat(id).isEqualTo("task");
                            return durable.get();
                        })
                .subscribe(
                        new Flow.Subscriber<>() {
                            @Override
                            public void onSubscribe(Flow.Subscription subscription) {
                                subscription.request(Long.MAX_VALUE);
                            }

                            @Override
                            public void onNext(StreamingEventKind event) {
                                events.add(event);
                            }

                            @Override
                            public void onError(Throwable error) {
                                fail("Expected durable terminal state", error);
                            }

                            @Override
                            public void onComplete() {
                                done.set(true);
                            }
                        });
        assertThat(staleWrites).hasValue(1);
        assertThat(done).isTrue();
        assertThat(events).hasSize(2);
        assertThat(events.get(0)).isSameAs(working);
        assertThat(((TaskStatusUpdateEvent) events.get(1)).status().state())
                .isEqualTo(TaskState.TASK_STATE_CANCELED);
        assertThat(durable.get().status().state()).isEqualTo(TaskState.TASK_STATE_CANCELED);
    }
}
