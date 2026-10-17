package com.a2alite.server;

import static org.assertj.core.api.Assertions.*;

import com.a2alite.runtime.RuntimeLimits;

import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.UnauthenticatedUser;
import org.junit.jupiter.api.Test;

import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.UnaryOperator;

class RuntimeControllerTest {
    @Test
    void onePrincipalCannotConsumeAnotherPrincipalsExecutionOrStreamQuota() {
        var limits =
                new RuntimeLimits(
                        4,
                        4,
                        4096,
                        4096,
                        10,
                        2,
                        1,
                        1,
                        100,
                        java.time.Duration.ofSeconds(5),
                        java.time.Duration.ofSeconds(5),
                        java.time.Duration.ofMillis(10));
        try (var controller = new RuntimeController(limits)) {
            var alice =
                    new ServerCallContext(
                            new org.a2aproject.sdk.server.auth.AuthenticatedUser("alice"),
                            Map.of(),
                            Set.of());
            var bob =
                    new ServerCallContext(
                            new org.a2aproject.sdk.server.auth.AuthenticatedUser("bob"),
                            Map.of(),
                            Set.of());
            try (var task = controller.admitTask(alice);
                    var stream = controller.admitStream(alice)) {
                assertThatThrownBy(() -> controller.admitTask(alice))
                        .isInstanceOf(RuntimeOverloadedException.class);
                assertThatThrownBy(() -> controller.admitStream(alice))
                        .isInstanceOf(RuntimeOverloadedException.class);
                try (var otherTask = controller.admitTask(bob);
                        var otherStream = controller.admitStream(bob)) {
                    assertThat(controller.metrics().get("activeTasks")).isEqualTo(2);
                }
            }
            try (var again = controller.admitTask(alice)) {
                assertThat(controller.metrics().get("activeTasks")).isEqualTo(1);
            }
        }
    }

    @Test
    void rejectedSubmissionReleasesClaimedButUnstartedAdmission() {
        try (var controller = new RuntimeController(RuntimeLimits.defaults())) {
            var context = new ServerCallContext(UnauthenticatedUser.INSTANCE, Map.of(), Set.of());
            var lease = controller.admitTask(context);
            var ran = new AtomicBoolean();
            @SuppressWarnings("unchecked")
            var wrapper =
                    (UnaryOperator<Runnable>)
                            context.getState().get(ServerCallContext.EXECUTION_WRAPPER_KEY);
            Runnable work = wrapper.apply(() -> ran.set(true));
            lease.abort();
            lease.close(); // executor rejected after wrapping, before starting
            work.run(); // a late executor must not run already rejected user work
            assertThat(ran).isFalse();
            assertThat(controller.metrics().get("activeTasks")).isEqualTo(0);
        }
    }
}
