package com.a2alite.server;

import com.a2alite.Agent;
import com.a2alite.AgentNetwork;
import com.a2alite.SkillConfig;
import com.a2alite.auth.AuthProvider;
import com.a2alite.auth.AuthResult;
import com.a2alite.auth.BearerAuth;
import com.a2alite.streaming.StreamingHandler;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.*;

class JavalinProtocolTest {
    private final ObjectMapper json = new ObjectMapper();
    private final HttpClient http = HttpClient.newHttpClient();
    private final JavalinServerAdapter server = new JavalinServerAdapter();
    private String url;

    @AfterEach
    void stop() { server.stop(); }

    @Test
    void validatesVersionAndPreservesNumericAndNullIds() throws Exception {
        var agent = agent(false);
        agent.skill("echo", p -> "hello");
        start(agent);
        var params = message("echo");
        var number = json.readTree("9007199254740993");
        var response = rpc("SendMessage", params, number, "1.0", null);
        assertThat(response.path("error").isMissingNode()).as(response.toString()).isTrue();
        assertThat(response.path("id")).isEqualTo(number);
        assertThat(response.path("result").path("message").path("parts").get(0).path("text").asText()).isEqualTo("hello");
        assertThat(rpc("SendMessage", params, json.nullNode(), "1.0", null).get("id").isNull()).isTrue();
        assertThat(rpc("SendMessage", params, number, null, null).has("error")).isTrue();
        assertThat(rpc("SendMessage", params, number, "0.3", null).has("error")).isTrue();
        assertThat(rpc("SendMessage", params, number, "2.0", null).path("id")).isEqualTo(number);
        assertThat(rpc("SendMessage", params, number, "not-a-version", null).has("error")).isTrue();
        assertThat(rpc("Unknown", json.createObjectNode(), number, "1.0", null).path("error").path("code").asInt()).isEqualTo(-32601);
        assertThat(rpc("GetTask", json.createObjectNode(), number, "1.0", null).has("error")).isTrue();
        assertThatThrownBy(() -> new AgentNetwork().callRemoteSkillWithHandle(url, "echo", Map.of(), 5))
            .hasMessageContaining("only a Message");
    }

    @Test
    void streamsSdkEventsAndPersistsCompletedTask() throws Exception {
        var agent = agent(true);
        agent.skill("stream", SkillConfig.withStreaming(), p -> StreamingHandler.fromIterator(List.of("one", "two").iterator()));
        start(agent);
        var body = request("SendStreamingMessage", message("stream"), json.getNodeFactory().numberNode(42));
        var response = send(body, "1.0", "alice");
        assertThat(response.headers().firstValue("content-type").orElse("")).contains("text/event-stream");
        var events = response.body().lines().filter(line -> line.startsWith("data: "))
            .map(line -> { try { return json.readTree(line.substring(6)); } catch (Exception e) { throw new RuntimeException(e); } }).toList();
        assertThat(events).isNotEmpty().allSatisfy(event -> {
            assertThat(event.path("id").asInt()).isEqualTo(42);
            assertThat(event.has("error")).as(event.toString()).isFalse();
        });
        String taskId = events.get(0).path("result").path("task").path("id").asText();
        assertThat(taskId).as(response.body()).isNotBlank();
        assertThat(response.body()).contains("one", "two", "TASK_STATE_COMPLETED");
        var task = rpc("GetTask", json.valueToTree(Map.of("id", taskId)), json.getNodeFactory().numberNode(1), "1.0", "alice");
        assertThat(task.path("result").path("status").path("state").asText()).as(task.toString()).isEqualTo("TASK_STATE_COMPLETED");
        assertThat(rpc("GetTask", json.valueToTree(Map.of("id", taskId)), json.getNodeFactory().numberNode(1), "1.0", "bob")
            .path("error").path("code").asInt()).isEqualTo(-32001);
        assertThat(rpc("CancelTask", json.valueToTree(Map.of("id", taskId)), json.getNodeFactory().numberNode(1), "1.0", "alice").has("error")).isTrue();
    }

    @Test
    void cancelsRunningTaskAndClosesProducerWithoutAllowingOtherUsers() throws Exception {
        var started = new CountDownLatch(1);
        var closed = new CountDownLatch(1);
        var agent = agent(true);
        agent.skill("wait", SkillConfig.withStreaming(), p -> StreamingHandler.stream(sink -> {
            try {
                started.countDown();
                new CountDownLatch(1).await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally { closed.countDown(); }
        }));
        start(agent);
        var params = message("wait");
        params.withObject("/configuration").put("returnImmediately", true);
        var result = rpc("SendMessage", params, json.getNodeFactory().numberNode(1), "1.0", "alice");
        String taskId = result.path("result").path("task").path("id").asText();
        assertThat(taskId).as(result.toString()).isNotBlank();
        assertThat(started.await(5, TimeUnit.SECONDS)).isTrue();
        var taskParams = json.valueToTree(Map.of("id", taskId));
        assertThat(rpc("CancelTask", taskParams, json.getNodeFactory().numberNode(2), "1.0", "bob").path("error").path("code").asInt()).isEqualTo(-32001);
        var canceled = rpc("CancelTask", taskParams, json.getNodeFactory().numberNode(3), "1.0", "alice");
        assertThat(canceled.path("result").path("status").path("state").asText()).as(canceled.toString()).isEqualTo("TASK_STATE_CANCELED");
        assertThat(closed.await(5, TimeUnit.SECONDS)).isTrue();
        assertThat(rpc("GetTask", taskParams, json.getNodeFactory().numberNode(4), "1.0", "alice")
            .path("result").path("status").path("state").asText()).isEqualTo("TASK_STATE_CANCELED");
    }

    @Test
    void scopesPushConfigurationsToAuthenticatedTaskOwnerAndConfigId() throws Exception {
        var agent = agent(true);
        agent.skill("task", SkillConfig.withStreaming(), p -> StreamingHandler.fromIterator(List.of("done").iterator()));
        start(agent);
        var created = rpc("SendMessage", message("task"), json.getNodeFactory().numberNode(1), "1.0", "alice");
        String taskId = created.path("result").path("task").path("id").asText();
        assertThat(taskId).as(created.toString()).isNotBlank();
        var config = json.valueToTree(Map.of("taskId", taskId, "id", "one", "url", "https://8.8.8.8/callback", "token", "secret"));
        assertThat(rpc("CreateTaskPushNotificationConfig", config, json.getNodeFactory().numberNode(1), "1.0", "bob").path("error").path("code").asInt()).isEqualTo(-32001);
        assertThat(rpc("CreateTaskPushNotificationConfig", config, json.getNodeFactory().numberNode(1), "1.0", "alice").path("result").path("id").asText()).isEqualTo("one");
        ((com.fasterxml.jackson.databind.node.ObjectNode) config).put("id", "two");
        assertThat(rpc("CreateTaskPushNotificationConfig", config, json.getNodeFactory().numberNode(1), "1.0", "alice").path("result").path("id").asText()).isEqualTo("two");
        var one = json.valueToTree(Map.of("taskId", taskId, "id", "one"));
        assertThat(rpc("GetTaskPushNotificationConfig", one, json.getNodeFactory().numberNode(1), "1.0", "bob").path("error").path("code").asInt()).isEqualTo(-32001);
        assertThat(rpc("DeleteTaskPushNotificationConfig", one, json.getNodeFactory().numberNode(1), "1.0", "alice").has("error")).isFalse();
        assertThat(rpc("GetTaskPushNotificationConfig", one, json.getNodeFactory().numberNode(1), "1.0", "alice").has("error")).isTrue();
        var list = rpc("ListTaskPushNotificationConfigs", json.valueToTree(Map.of("taskId", taskId)), json.getNodeFactory().numberNode(1), "1.0", "alice");
        assertThat(list.path("result").path("configs")).as(list.toString()).hasSize(1);
        assertThat(list.path("result").path("configs").get(0).path("id").asText()).isEqualTo("two");
        ((com.fasterxml.jackson.databind.node.ObjectNode) config).put("taskId", "missing-task");
        assertThat(rpc("CreateTaskPushNotificationConfig", config, json.getNodeFactory().numberNode(1), "1.0", "alice").path("error").path("code").asInt()).isEqualTo(-32001);
    }

    @Test
    void rejectsPrivateCallbacksBeforeSkillRunsAndRequiresIdentity() throws Exception {
        var calls = new AtomicInteger();
        var agent = agent(true);
        agent.skill("task", SkillConfig.withStreaming(), p -> { calls.incrementAndGet(); return "done"; });
        start(agent);
        for (String target : List.of("http://127.0.0.1/callback", "http://169.254.169.254/", "http://[::ffff:127.0.0.1]/", "https://user:pass@8.8.8.8/", "file:///tmp/callback")) {
            var params = message("task");
            params.withObject("/configuration").set("taskPushNotificationConfig", json.valueToTree(Map.of("url", target)));
            var result = rpc("SendMessage", params, json.getNodeFactory().numberNode(1), "1.0", "alice");
            assertThat(result.path("error").path("code").asInt()).as(result.toString()).isEqualTo(-32602);
        }
        assertThat(calls).hasValue(0);
        assertThat(send(request("SendMessage", message("task"), json.getNodeFactory().numberNode(1)), "1.0", null).statusCode()).isEqualTo(401);
    }

    @Test
    void anonymousTasksCannotRegisterCallbacks() throws Exception {
        var agent = agent(false);
        agent.skill("task", SkillConfig.withStreaming(), p -> "done");
        start(agent);
        var created = rpc("SendMessage", message("task"), json.getNodeFactory().numberNode(1), "1.0", null);
        String taskId = created.path("result").path("task").path("id").asText();
        assertThat(taskId).as(created.toString()).isNotBlank();
        var config = json.valueToTree(Map.of("taskId", taskId, "url", "https://8.8.8.8/callback"));
        assertThat(rpc("CreateTaskPushNotificationConfig", config, json.getNodeFactory().numberNode(1), "1.0", null).has("error")).isTrue();
    }

    @Test
    void taskContextUsesProtocolTaskIdAndEmitsProgress() throws Exception {
        var agent = agent(false);
        var reportedId = new java.util.concurrent.atomic.AtomicReference<String>();
        agent.skill("context", (com.a2alite.SkillHandlerWithContext) (params, context) -> {
            reportedId.set(context.getTaskId());
            context.update(com.a2alite.TaskState.WORKING, "halfway", 0.5);
            return "done";
        });
        start(agent);
        var result = rpc("SendMessage", message("context"), json.getNodeFactory().numberNode(1), "1.0", null);
        var task = result.path("result").path("task");
        assertThat(task.path("id").asText()).as(result.toString()).isEqualTo(reportedId.get());
        assertThat(task.path("status").path("state").asText()).isEqualTo("TASK_STATE_COMPLETED");
        assertThat(task.path("status").path("message").path("parts").get(0).path("text").asText()).isEqualTo("done");
        assertThat(rpc("GetTask", json.valueToTree(Map.of("id", reportedId.get())), json.getNodeFactory().numberNode(2), "1.0", null).has("error")).isFalse();
    }

    @Test
    void configuredAuthWithoutIdentityFailsClosed() throws Exception {
        var agent = Agent.builder().name("Auth").description("identity required").auth(new AuthProvider() {
            @Override public AuthResult authenticate(com.a2alite.auth.AuthRequest request) { return AuthResult.success("  "); }
            @Override public Map<String, Object> getScheme() { return Map.of(); }
        }).build();
        agent.skill("echo", p -> "hello");
        start(agent);
        assertThat(send(request("SendMessage", message("echo"), json.getNodeFactory().numberNode(1)), "1.0", null).statusCode()).isEqualTo(401);
    }

    @Test
    void fastBlockingTasksCompleteWithoutConsumptionTimeout() throws Exception {
        var agent = agent(false);
        agent.skill("fast", SkillConfig.withStreaming(), params -> "done");
        start(agent);
        for (int i = 0; i < 30; i++) {
            var response = rpc("SendMessage", message("fast"), json.getNodeFactory().numberNode(i), "1.0", null);
            assertThat(response.path("result").path("task").path("status").path("state").asText())
                .as(response.toString()).isEqualTo("TASK_STATE_COMPLETED");
        }
    }

    @Test
    void compositeAnonymousFallbackCannotRegisterPushCallbacks() throws Exception {
        var agent = Agent.builder().name("Optional auth").description("Composite fallback")
            .auth(new com.a2alite.auth.CompositeAuth(List.of(new BearerAuth(token -> "alice"), new com.a2alite.auth.NoAuth())))
            .build();
        agent.skill("task", SkillConfig.withStreaming(), params -> "done");
        start(agent);
        var response = rpc("SendMessage", message("task"), json.getNodeFactory().numberNode(1), "1.0", null);
        String taskId = response.path("result").path("task").path("id").asText();
        assertThat(taskId).as(response.toString()).isNotBlank();
        var config = json.valueToTree(Map.of("taskId", taskId, "url", "https://8.8.8.8/callback"));
        assertThat(rpc("CreateTaskPushNotificationConfig", config, json.getNodeFactory().numberNode(2), "1.0", null).has("error")).isTrue();
        assertThat(rpc("CreateTaskPushNotificationConfig", config, json.getNodeFactory().numberNode(2), "1.0", "alice").has("error")).isTrue();
    }

    @Test
    void networkSendsHeadersOnlyToConfiguredEndpoint() throws Exception {
        var agent = agent(true);
        agent.skill("task", SkillConfig.withStreaming(), params -> "done");
        start(agent);
        var network = new AgentNetwork().withHeaders(url, Map.of("Authorization", "Bearer alice"));
        var handle = network.callRemoteSkillWithHandle(url, "task", Map.of(), 5);
        assertThat(handle.getTaskId()).isNotBlank();
        assertThat(handle.getStatus()).isNotNull();
        handle.subscribe("https://8.8.8.8/callback");
        assertThat(handle.getPushConfig()).isNotNull();
        handle.unsubscribe();
        assertThatThrownBy(() -> network.callRemoteSkill(url + "?unconfigured", "task", Map.of(), 5))
            .hasMessageContaining("HTTP 401");
    }

    @Test
    void streamingErrorsBeginWithTaskSnapshot() throws Exception {
        var agent = agent(false);
        agent.skill("stream", SkillConfig.withStreaming(), params -> "done");
        agent.skill("fail", params -> { throw new IllegalStateException("failure"); });
        agent.skill("middleware", params -> "unreachable");
        agent.use((context, next) -> {
            if ("middleware".equals(context.skill())) throw new IllegalStateException("middleware failure");
            return next.call();
        });
        start(agent);
        for (String skill : List.of("fail", "missing", "middleware")) {
            var response = send(request("SendStreamingMessage", message(skill), json.getNodeFactory().numberNode(1)), "1.0", null);
            String first = response.body().lines().filter(line -> line.startsWith("data: ")).findFirst().orElseThrow();
            var initial = json.readTree(first.substring(6)).path("result").path("task");
            assertThat(initial.path("id").asText()).as(response.body()).isNotBlank();
            assertThat(response.body()).contains("TASK_STATE_FAILED");
        }
    }

    private Agent agent(boolean authenticated) {
        var builder = Agent.builder().name("Test").description("HTTP integration");
        if (authenticated) builder.auth(new BearerAuth(token -> List.of("alice", "bob").contains(token) ? token : null));
        return builder.build();
    }

    private void start(Agent agent) {
        server.start(agent, "127.0.0.1", 0);
        url = "http://127.0.0.1:" + server.port() + "/";
    }

    private com.fasterxml.jackson.databind.node.ObjectNode message(String skill) {
        return json.valueToTree(Map.of("message", Map.of("messageId", UUID.randomUUID().toString(), "role", "ROLE_USER",
            "parts", List.of(Map.of("text", "{\"skill\":\"" + skill + "\"}")))));
    }

    private String request(String method, JsonNode params, JsonNode id) throws Exception {
        var body = json.createObjectNode().put("jsonrpc", "2.0").put("method", method);
        body.set("id", id);
        body.set("params", params);
        return json.writeValueAsString(body);
    }

    private JsonNode rpc(String method, JsonNode params, JsonNode id, String version, String user) throws Exception {
        return json.readTree(send(request(method, params, id), version, user).body());
    }

    private HttpResponse<String> send(String body, String version, String user) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create(url)).header("Content-Type", "application/json")
            .timeout(Duration.ofSeconds(15)).POST(HttpRequest.BodyPublishers.ofString(body));
        if (version != null) builder.header("A2A-Version", version);
        if (user != null) builder.header("Authorization", "Bearer " + user);
        return http.send(builder.build(), HttpResponse.BodyHandlers.ofString());
    }
}
