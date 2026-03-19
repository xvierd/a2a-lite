package com.a2alite;

import com.a2alite.push.PushNotifier;
import com.a2alite.testing.AgentTestClient;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

/**
 * Tests that verify Agent.Builder accepts a PushNotifier and that the notifier
 * is called after a skill completes.
 */
class AgentPushNotifierTest {

    // -------------------------------------------------------------------------
    // Builder acceptance tests
    // -------------------------------------------------------------------------

    @Test
    void builderAcceptsPushNotifierWithoutError() {
        PushNotifier notifier = event -> {};

        assertThatCode(() -> Agent.builder()
            .name("Bot")
            .description("Test")
            .pushNotifier(notifier)
            .build()
        ).doesNotThrowAnyException();
    }

    @Test
    void builderAcceptsNullPushNotifier() {
        assertThatCode(() -> Agent.builder()
            .name("Bot")
            .description("Test")
            .pushNotifier(null)
            .build()
        ).doesNotThrowAnyException();
    }

    // -------------------------------------------------------------------------
    // Notifier invocation tests
    // -------------------------------------------------------------------------

    @Test
    void notifierIsCalledAfterSkillCompletes() throws Exception {
        AtomicBoolean called = new AtomicBoolean(false);
        CountDownLatch latch = new CountDownLatch(1);

        PushNotifier notifier = event -> {
            called.set(true);
            latch.countDown();
        };

        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .pushNotifier(notifier)
            .build();

        agent.skill("echo", params -> params.get("msg"));

        var client = new AgentTestClient(agent);
        client.call("echo", Map.of("msg", "hello"));

        assertThat(latch.await(2, TimeUnit.SECONDS)).isTrue();
        assertThat(called.get()).isTrue();
    }

    @Test
    void notifierReceivesSkillNameInEvent() throws Exception {
        AtomicReference<Map<String, Object>> captured = new AtomicReference<>();
        CountDownLatch latch = new CountDownLatch(1);

        PushNotifier notifier = event -> {
            captured.set(event);
            latch.countDown();
        };

        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .pushNotifier(notifier)
            .build();

        agent.skill("greet", params -> "Hello!");

        var client = new AgentTestClient(agent);
        client.call("greet", Map.of());

        assertThat(latch.await(2, TimeUnit.SECONDS)).isTrue();
        assertThat(captured.get()).isNotNull();
        assertThat(captured.get()).containsKey("skill");
        assertThat(captured.get().get("skill")).isEqualTo("greet");
    }

    @Test
    void notifierReceivesSkillResult() throws Exception {
        AtomicReference<Map<String, Object>> captured = new AtomicReference<>();
        CountDownLatch latch = new CountDownLatch(1);

        PushNotifier notifier = event -> {
            captured.set(event);
            latch.countDown();
        };

        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .pushNotifier(notifier)
            .build();

        agent.skill("sum", params -> 42);

        var client = new AgentTestClient(agent);
        client.call("sum", Map.of());

        assertThat(latch.await(2, TimeUnit.SECONDS)).isTrue();
        assertThat(captured.get()).containsKey("result");
        assertThat(captured.get().get("result")).isEqualTo(42);
    }

    @Test
    void notifierIsCalledOncePerSkillInvocation() throws Exception {
        List<Map<String, Object>> events = new ArrayList<>();
        CountDownLatch latch = new CountDownLatch(3);

        PushNotifier notifier = event -> {
            synchronized (events) {
                events.add(event);
            }
            latch.countDown();
        };

        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .pushNotifier(notifier)
            .build();

        agent.skill("ping", params -> "pong");

        var client = new AgentTestClient(agent);
        client.call("ping", Map.of());
        client.call("ping", Map.of());
        client.call("ping", Map.of());

        assertThat(latch.await(3, TimeUnit.SECONDS)).isTrue();
        assertThat(events).hasSize(3);
    }

    @Test
    void notifierNotSetMeansSkillStillWorks() throws Exception {
        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .build();

        agent.skill("echo", params -> params.get("msg"));

        var client = new AgentTestClient(agent);
        var result = client.call("echo", Map.of("msg", "world"));
        assertThat(result.getData()).isEqualTo("world");
    }

    @Test
    void builderFluentChainReturnsBuilder() {
        // Verify the pushNotifier() method returns the Builder for fluent chaining
        Agent.Builder builder = Agent.builder()
            .name("Bot")
            .description("Test");

        Agent.Builder returned = builder.pushNotifier(event -> {});
        assertThat(returned).isSameAs(builder);
    }
}
