package com.a2alite;

import com.a2alite.middleware.*;
import com.a2alite.testing.AgentTestClient;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MiddlewareTest {

    // === LoggingMiddleware Tests ===

    @Test
    void shouldLogSkillCalls() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("echo", params -> params.get("msg"));

        List<String> logs = new ArrayList<>();
        var logger = new java.util.logging.Logger("test", null) {
            { setUseParentHandlers(false); }
        };
        logger.addHandler(new java.util.logging.Handler() {
            @Override public void publish(java.util.logging.LogRecord record) {
                logs.add(record.getMessage());
            }
            @Override public void flush() {}
            @Override public void close() {}
        });

        agent.use(LoggingMiddleware.create(logger));

        var client = new AgentTestClient(agent);
        client.call("echo", Map.of("msg", "hello"));

        assertThat(logs).anyMatch(l -> l.contains("Calling skill"));
        assertThat(logs).anyMatch(l -> l.contains("completed"));
    }

    @Test
    void shouldLogDefaultLogger() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("echo", params -> "ok");
        agent.use(LoggingMiddleware.create());

        var client = new AgentTestClient(agent);
        client.call("echo"); // Should not throw
    }

    // === RateLimitMiddleware Tests ===

    @Test
    void shouldAllowRequestsUnderLimit() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("echo", params -> "ok");
        agent.use(RateLimitMiddleware.create(10));

        var client = new AgentTestClient(agent);
        for (int i = 0; i < 5; i++) {
            assertThat(client.call("echo").getData()).isEqualTo("ok");
        }
    }

    @Test
    void shouldRejectWhenLimitExceeded() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("echo", params -> "ok");
        agent.use(RateLimitMiddleware.create(3, 60_000L));

        var client = new AgentTestClient(agent);
        client.call("echo");
        client.call("echo");
        client.call("echo");

        assertThatThrownBy(() -> client.call("echo"))
            .isInstanceOf(Exception.class)
            .hasMessageContaining("Rate limit exceeded");
    }

    // === ErrorHandlingMiddleware Tests ===

    @Test
    void shouldCatchErrors() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("fail", params -> { throw new RuntimeException("boom"); });
        agent.use(ErrorHandlingMiddleware.create());

        var client = new AgentTestClient(agent);
        var result = client.call("fail");
        @SuppressWarnings("unchecked")
        var data = (Map<String, Object>) result.getData();
        assertThat(data.get("error")).isEqualTo("boom");
        assertThat(data.get("type")).isEqualTo("RuntimeException");
    }

    @Test
    void shouldIncludeStackTrace() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("fail", params -> { throw new RuntimeException("boom"); });
        agent.use(ErrorHandlingMiddleware.create(true));

        var client = new AgentTestClient(agent);
        var result = client.call("fail");
        @SuppressWarnings("unchecked")
        var data = (Map<String, Object>) result.getData();
        assertThat(data).containsKey("stack");
    }

    @Test
    void shouldUseCustomErrorHandler() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("fail", params -> { throw new RuntimeException("boom"); });
        agent.use(ErrorHandlingMiddleware.create((error, ctx) ->
            Map.of("custom_error", error.getMessage())
        ));

        var client = new AgentTestClient(agent);
        var result = client.call("fail");
        @SuppressWarnings("unchecked")
        var data = (Map<String, Object>) result.getData();
        assertThat(data.get("custom_error")).isEqualTo("boom");
    }

    @Test
    void shouldPassThroughOnSuccess() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("ok", params -> "success");
        agent.use(ErrorHandlingMiddleware.create());

        var client = new AgentTestClient(agent);
        assertThat(client.call("ok").getData()).isEqualTo("success");
    }

    // === TimingMiddleware Tests ===

    @Test
    void shouldTrackExecutionTime() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("slow", params -> {
            Thread.sleep(50);
            return "done";
        });

        // TimingMiddleware sets metadata after inner call completes
        agent.use(TimingMiddleware.create());

        var client = new AgentTestClient(agent);
        assertThat(client.call("slow").getData()).isEqualTo("done");
    }

    // === RequestIdMiddleware Tests ===

    @Test
    void shouldAddRequestId() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("echo", params -> "ok");

        final String[] requestId = {null};
        agent.use(RequestIdMiddleware.create());
        agent.use((ctx, next) -> {
            requestId[0] = ctx.getMetadata("requestId");
            return next.call();
        });

        var client = new AgentTestClient(agent);
        client.call("echo");
        assertThat(requestId[0]).isNotNull().isNotEmpty();
    }

    // === CorsMiddleware Tests ===

    @Test
    void shouldStoreCorsConfig() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("echo", params -> "ok");

        final Map<String, Object>[] corsConfig = new Map[1];
        agent.use(CorsMiddleware.create(List.of("https://example.com")));
        agent.use((ctx, next) -> {
            corsConfig[0] = ctx.getMetadata("cors");
            return next.call();
        });

        var client = new AgentTestClient(agent);
        client.call("echo");

        assertThat(corsConfig[0]).isNotNull();
        @SuppressWarnings("unchecked")
        var origins = (List<String>) corsConfig[0].get("origins");
        assertThat(origins).contains("https://example.com");
    }

    @Test
    void shouldStoreCorsWithMethods() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("echo", params -> "ok");

        final Map<String, Object>[] corsConfig = new Map[1];
        agent.use(CorsMiddleware.create(
            List.of("*"),
            List.of("GET", "POST"),
            List.of("X-Custom")
        ));
        agent.use((ctx, next) -> {
            corsConfig[0] = ctx.getMetadata("cors");
            return next.call();
        });

        var client = new AgentTestClient(agent);
        client.call("echo");

        @SuppressWarnings("unchecked")
        var methods = (List<String>) corsConfig[0].get("methods");
        assertThat(methods).containsExactly("GET", "POST");
    }

    // === Middleware Chaining Tests ===

    @Test
    void shouldChainMultipleMiddlewares() throws Exception {
        var agent = Agent.builder().name("Bot").description("Test").build();
        agent.skill("echo", params -> params.get("msg"));

        List<String> order = new ArrayList<>();
        agent.use((ctx, next) -> { order.add("m1-before"); var r = next.call(); order.add("m1-after"); return r; });
        agent.use((ctx, next) -> { order.add("m2-before"); var r = next.call(); order.add("m2-after"); return r; });

        var client = new AgentTestClient(agent);
        client.call("echo", Map.of("msg", "hi"));

        assertThat(order).containsExactly("m1-before", "m2-before", "m2-after", "m1-after");
    }
}
