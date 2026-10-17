package com.a2alite.server;

import static org.assertj.core.api.Assertions.*;

import com.a2alite.runtime.RuntimeLimits;

import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.*;
import org.a2aproject.sdk.spec.*;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.*;

class InMemoryProtocolBackendTest {
    @Test
    void capacityEvictsOnlyFinalTasksTogetherWithOwnershipAndCallbackSecrets() throws Exception {
        var limits =
                new RuntimeLimits(
                        2,
                        2,
                        4096,
                        4096,
                        2,
                        2,
                        1,
                        1,
                        2,
                        Duration.ofSeconds(5),
                        Duration.ofSeconds(5),
                        Duration.ofSeconds(1));
        try (var backend = new InMemoryProtocolBackend(limits)) {
            var context = new ServerCallContext(new AuthenticatedUser("alice"), Map.of(), Set.of());
            for (String id : List.of("final", "active")) {
                backend.authorization().recordOwnership(context, id, TaskOperation.MESSAGE_SEND);
                var history = new ArrayList<Message>();
                for (int i = 0; i < 5; i++)
                    history.add(
                            Message.builder()
                                    .messageId("message-" + i)
                                    .role(Message.Role.ROLE_USER)
                                    .parts(List.of(new TextPart("hello")))
                                    .build());
                backend.tasks()
                        .save(
                                Task.builder()
                                        .id(id)
                                        .contextId("ctx")
                                        .status(
                                                new TaskStatus(
                                                        id.equals("final")
                                                                ? TaskState.TASK_STATE_COMPLETED
                                                                : TaskState.TASK_STATE_WORKING))
                                        .history(history)
                                        .build(),
                                false);
            }
            backend.pushConfigs()
                    .setInfo(
                            TaskPushNotificationConfig.builder()
                                    .taskId("final")
                                    .id("secret")
                                    .url("https://example.com/hook")
                                    .token("secret-token")
                                    .build());
            assertThat(backend.tasks().get("active").history()).hasSize(2);
            assertThatThrownBy(
                            () ->
                                    backend.authorization()
                                            .recordOwnership(
                                                    context, "next", TaskOperation.MESSAGE_SEND))
                    .isInstanceOf(RuntimeOverloadedException.class);
            Thread.sleep(1100); // finalized response grace period, not an active-task TTL
            backend.authorization().recordOwnership(context, "next", TaskOperation.MESSAGE_SEND);
            assertThat(backend.tasks().get("final")).isNull();
            assertThat(backend.authorization().isTaskRecorded("final")).isFalse();
            assertThat(
                            backend.pushConfigs()
                                    .getInfo(new ListTaskPushNotificationConfigsParams("final"))
                                    .configs())
                    .isEmpty();
            assertThat(backend.tasks().get("active")).isNotNull();
            assertThatThrownBy(
                            () ->
                                    backend.authorization()
                                            .recordOwnership(
                                                    context,
                                                    "overflow",
                                                    TaskOperation.MESSAGE_SEND))
                    .isInstanceOf(RuntimeOverloadedException.class);
        }
    }
}
