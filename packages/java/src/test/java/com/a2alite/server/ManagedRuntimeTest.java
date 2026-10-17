package com.a2alite.server;

import static org.assertj.core.api.Assertions.*;

import com.a2alite.*;
import com.a2alite.auth.*;
import com.a2alite.runtime.*;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.*;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;

class ManagedRuntimeTest {
    private final ObjectMapper json = new ObjectMapper();
    private final HttpClient http = HttpClient.newHttpClient();

    @Test
    void profilesFailClosedBeforeStartupHooks() {
        var starts = new AtomicInteger();
        var agent =
                Agent.builder()
                        .name("private")
                        .description("test")
                        .runtimeOptions(RuntimeOptions.authenticated())
                        .build()
                        .onStartup(starts::incrementAndGet);
        assertThatThrownBy(() -> agent.start(0)).hasMessageContaining("authentication");
        assertThat(starts).hasValue(0);
        var durable =
                Agent.builder()
                        .name("durable")
                        .description("test")
                        .auth(new APIKeyAuth(Set.of("key")))
                        .runtimeOptions(RuntimeOptions.durable())
                        .build();
        assertThatThrownBy(() -> durable.start(0)).hasMessageContaining("backend");
    }

    @Test
    void credentialsRotateWithoutChangingTaskOwnershipAndTenantsRemainIsolated() throws Exception {
        var alice =
                AuthResult.identified("issuer-one", "alice", Set.of("", "red", "blue"), Set.of());
        var issuerTwo = AuthResult.identified("issuer-two", "alice", Set.of("red"), Set.of());
        var agent =
                Agent.builder()
                        .name("identified")
                        .description("test")
                        .auth(
                                new APIKeyAuth(
                                        Map.of("old", alice, "new", alice, "other", issuerTwo)))
                        .runtimeOptions(RuntimeOptions.authenticated())
                        .build();
        agent.skill("task", (params, task) -> task.getTaskId());
        try (var runtime = agent.start("127.0.0.1", 0)) {
            String url = "http://127.0.0.1:" + runtime.port();
            var key = new AtomicReference<>("old");
            var network =
                    new AgentNetwork()
                            .withCredentials(url, destination -> Map.of("X-API-Key", key.get()));
            var handle = network.callRemoteSkillWithHandle(url, "task", Map.of(), 5);
            assertThat(handle.getResult()).isEqualTo(handle.getTaskId());
            key.set("new");
            assertThat(((Map<?, ?>) handle.get()).get("id")).isEqualTo(handle.getTaskId());
            String params =
                    "{\"tenant\":\"red\",\"message\":{\"role\":\"ROLE_USER\",\"messageId\":\"m\",\"parts\":[{\"text\":\"{\\\"skill\\\":\\\"task\\\"}\"}]}}";
            var sent = rpc(url, "SendMessage", params, "old");
            String id = json.readTree(sent.body()).path("result").path("task").path("id").asText();
            assertThat(id).as(sent.body()).isNotEmpty();
            assertThat(
                            json.readTree(
                                            rpc(
                                                            url,
                                                            "GetTask",
                                                            "{\"id\":\""
                                                                    + id
                                                                    + "\",\"tenant\":\"red\"}",
                                                            "new")
                                                    .body())
                                    .has("result"))
                    .isTrue();
            for (String tenant : List.of("blue", "")) {
                assertThat(
                                json.readTree(
                                                rpc(
                                                                url,
                                                                "GetTask",
                                                                "{\"id\":\""
                                                                        + id
                                                                        + "\",\"tenant\":\""
                                                                        + tenant
                                                                        + "\"}",
                                                                "new")
                                                        .body())
                                        .has("error"))
                        .isTrue();
            }
            assertThat(
                            json.readTree(
                                            rpc(
                                                            url,
                                                            "GetTask",
                                                            "{\"id\":\""
                                                                    + id
                                                                    + "\",\"tenant\":\"red\"}",
                                                            "other")
                                                    .body())
                                    .has("error"))
                    .isTrue();
            var listed =
                    json.readTree(rpc(url, "ListTasks", "{\"tenant\":\"blue\"}", "new").body());
            assertThat(listed.path("result").path("tasks")).isEmpty();
        }
    }

    @Test
    void saturatingTasksKeepsReadsAvailableAndCloseDrainsOnce() throws Exception {
        var started = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var hooks = new AtomicInteger();
        var limits =
                new RuntimeLimits(
                        1,
                        1,
                        4096,
                        4096,
                        10,
                        2,
                        Duration.ofSeconds(10),
                        Duration.ofSeconds(10),
                        Duration.ofSeconds(2));
        var agent =
                Agent.builder()
                        .name("bounded")
                        .description("test")
                        .runtimeOptions(new RuntimeOptions(RuntimeOptions.Profile.LEARNING, limits))
                        .build()
                        .onShutdown(hooks::incrementAndGet);
        agent.skill(
                "wait",
                SkillConfig.withTask(),
                params -> {
                    started.countDown();
                    release.await();
                    return "done";
                });
        var runtime = agent.start("127.0.0.1", 0);
        String url = "http://127.0.0.1:" + runtime.port();
        var network = new AgentNetwork();
        var call =
                CompletableFuture.supplyAsync(
                        () -> {
                            try {
                                return network.callRemoteSkillWithHandle(url, "wait", Map.of(), 5);
                            } catch (Exception e) {
                                throw new RuntimeException(e);
                            }
                        });
        try {
            assertThat(started.await(3, TimeUnit.SECONDS)).isTrue();
            assertThat(rpc(url, "SendMessage", "{}", null).statusCode()).isEqualTo(503);
            assertThat(rpc(url, "GetTask", "{\"id\":\"missing\"}", null).statusCode())
                    .isEqualTo(200);
            assertThat(runtime.metrics().get("activeTasks")).isEqualTo(1);
            release.countDown();
            assertThat(call.get(3, TimeUnit.SECONDS).getResult()).isEqualTo("done");
        } finally {
            release.countDown();
            runtime.close();
            runtime.close();
        }
        assertThat(hooks).hasValue(1);
        assertThat(runtime.ready()).isFalse();
        assertThat(runtime.metrics().get("activeTasks")).isEqualTo(0);
    }

    @Test
    void shutdownHookCannotBlockTheHostingProcessBeyondItsGrace() throws Exception {
        var hookEntered = new CountDownLatch(1);
        var release = new CountDownLatch(1);
        var limits =
                new RuntimeLimits(
                        2,
                        2,
                        4096,
                        4096,
                        10,
                        2,
                        Duration.ofSeconds(2),
                        Duration.ofSeconds(2),
                        Duration.ofMillis(100));
        var agent =
                Agent.builder()
                        .name("hook-limit")
                        .description("test")
                        .runtimeOptions(new RuntimeOptions(RuntimeOptions.Profile.LEARNING, limits))
                        .build();
        agent.onShutdown(
                () -> {
                    hookEntered.countDown();
                    while (release.getCount() > 0) {
                        try {
                            release.await();
                        } catch (InterruptedException ignored) {
                        }
                    }
                });
        var runtime = agent.start("127.0.0.1", 0);
        try {
            long started = System.nanoTime();
            runtime.close();
            assertThat(Duration.ofNanos(System.nanoTime() - started))
                    .isLessThan(Duration.ofSeconds(1));
            assertThat(hookEntered.await(1, TimeUnit.SECONDS)).isTrue();
            assertThat(runtime.metrics().get("shutdownCleanupRunning")).isEqualTo(true);
            assertThat(runtime.ready()).isFalse();
        } finally {
            release.countDown();
        }
    }

    @Test
    void oversizedHttpBodyReturns413BeforeSkillExecution() throws Exception {
        var limits =
                new RuntimeLimits(
                        2,
                        2,
                        256,
                        4096,
                        10,
                        2,
                        Duration.ofSeconds(2),
                        Duration.ofSeconds(2),
                        Duration.ofSeconds(1));
        var calls = new AtomicInteger();
        var agent =
                Agent.builder()
                        .name("body-limit")
                        .description("test")
                        .runtimeOptions(new RuntimeOptions(RuntimeOptions.Profile.LEARNING, limits))
                        .build();
        agent.skill("never", params -> calls.incrementAndGet());
        try (var runtime = agent.start("127.0.0.1", 0)) {
            var response =
                    rpc(
                            "http://127.0.0.1:" + runtime.port(),
                            "SendMessage",
                            "{\"oversized\":\"" + "x".repeat(300) + "\"}",
                            null);
            assertThat(response.statusCode()).as(response.body()).isEqualTo(413);
            assertThat(calls).hasValue(0);
        }
    }

    @Test
    void emptyStreamingAndTaskContextUpdatesConsumeTheOutputBudget() throws Exception {
        var limits =
                new RuntimeLimits(
                        2,
                        2,
                        4096,
                        64,
                        10,
                        2,
                        2,
                        2,
                        100,
                        8,
                        Duration.ofSeconds(5),
                        Duration.ofSeconds(5),
                        Duration.ofSeconds(1));
        var emitted = new AtomicInteger();
        var agent =
                Agent.builder()
                        .name("event-limit")
                        .description("test")
                        .runtimeOptions(new RuntimeOptions(RuntimeOptions.Profile.LEARNING, limits))
                        .build();
        agent.skill(
                "empty",
                SkillConfig.withStreaming(),
                params ->
                        com.a2alite.streaming.StreamingHandler.fromIterator(
                                new Iterator<String>() {
                                    public boolean hasNext() {
                                        return true;
                                    }

                                    public String next() {
                                        emitted.incrementAndGet();
                                        return "";
                                    }
                                }));
        agent.skill(
                "status",
                (params, task) -> {
                    task.update(com.a2alite.TaskState.WORKING, "x".repeat(1000), 0.5);
                    return "ignored";
                });
        agent.skill(
                "progress",
                (params, task) -> {
                    for (int i = 0; i < 100; i++)
                        task.update(com.a2alite.TaskState.WORKING, "", 0.5);
                    return "ignored";
                });
        try (var runtime = agent.start("127.0.0.1", 0)) {
            String url = "http://127.0.0.1:" + runtime.port();
            var network = new AgentNetwork();
            for (String skill : List.of("empty", "status", "progress")) {
                var handle = network.callRemoteSkillWithHandle(url, skill, Map.of(), 5);
                var task = json.valueToTree(handle.get());
                assertThat(task.path("status").path("state").asText())
                        .as(skill + task.toString())
                        .isEqualTo("TASK_STATE_FAILED");
                assertThat(task.toString()).doesNotContain("x".repeat(100));
            }
            assertThat(emitted)
                    .hasValue(9); // attempt after the eighth empty chunk fails immediately
        }
    }

    @Test
    void deadlineInterruptsCooperativeSkillAndCapsResult() throws Exception {
        var interrupted = new CountDownLatch(1);
        var limits =
                new RuntimeLimits(
                        2,
                        2,
                        4096,
                        32,
                        10,
                        2,
                        Duration.ofMillis(100),
                        Duration.ofSeconds(2),
                        Duration.ofSeconds(1));
        var agent =
                Agent.builder()
                        .name("deadline")
                        .description("test")
                        .runtimeOptions(new RuntimeOptions(RuntimeOptions.Profile.LEARNING, limits))
                        .build();
        agent.skill(
                "sleep",
                SkillConfig.withTask(),
                params -> {
                    try {
                        Thread.sleep(10_000);
                    } catch (InterruptedException e) {
                        interrupted.countDown();
                        throw e;
                    }
                    return "late";
                });
        agent.skill("big", SkillConfig.withTask(), params -> "x".repeat(33));
        try (var runtime = agent.start("127.0.0.1", 0)) {
            String url = "http://127.0.0.1:" + runtime.port();
            var network = new AgentNetwork();
            var sleeping = network.callRemoteSkillWithHandle(url, "sleep", Map.of(), 5);
            assertThat(interrupted.await(1, TimeUnit.SECONDS)).isTrue();
            assertThat(json.valueToTree(sleeping.get()).path("status").path("state").asText())
                    .isEqualTo("TASK_STATE_FAILED");
            var large = network.callRemoteSkillWithHandle(url, "big", Map.of(), 5);
            assertThat(json.valueToTree(large.get()).path("status").path("state").asText())
                    .isEqualTo("TASK_STATE_FAILED");
        }
    }

    private HttpResponse<String> rpc(String url, String method, String params, String key)
            throws Exception {
        var request =
                HttpRequest.newBuilder(URI.create(url))
                        .timeout(Duration.ofSeconds(5))
                        .header("Content-Type", "application/json")
                        .header("A2A-Version", "1.0");
        if (key != null) request.header("x-ApI-kEy", key);
        return http.send(
                request.POST(
                                HttpRequest.BodyPublishers.ofString(
                                        "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\""
                                                + method
                                                + "\",\"params\":"
                                                + params
                                                + "}"))
                        .build(),
                HttpResponse.BodyHandlers.ofString());
    }
}
