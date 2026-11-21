package com.a2alite.server;

import com.a2alite.Agent;
import com.a2alite.AgentRouter;
import com.a2alite.SkillConfig;
import com.a2alite.auth.BearerAuth;
import com.a2alite.runtime.RuntimeOptions;
import com.a2alite.streaming.StreamingHandler;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.*;

class AgentRouterTest {
    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();
    private static final long ID = 9007199254740993L;
    private static final String CARD = "/.well-known/agent-card.json";

    @Test
    void discoversAndCallsTwoIsolatedAgentsOnTheirAdvertisedUrls() throws Exception {
        var closed = new AtomicInteger();
        var publicAgent = Agent.builder().name("Echo").description("Free text").textEntrySkill("echo").build()
            .skill("echo", p -> p.get("message"))
            .skill("ping", SkillConfig.of("Ping", List.of("health")), p -> "pong")
            .onShutdown(closed::incrementAndGet);
        var privateAgent = Agent.builder().name("Stream").description("Private tasks")
            .auth(new BearerAuth(token -> "key".equals(token) ? "alice" : null)).build()
            .skill("read", SkillConfig.withStreaming(), p -> StreamingHandler.fromIterator(List.of("one", "two").iterator()))
            .skill("ping", p -> "private").onShutdown(closed::incrementAndGet);
        try (var router = new AgentRouter().mount("/echo/", publicAgent).mount("services/stream", privateAgent)) {
            router.run("127.0.0.1", 0);
            String root = "http://127.0.0.1:" + router.port();
            var directory = get(root + "/").path("agents");
            assertThat(directory.size()).isEqualTo(2);
            var first = get(root + directory.get(0).get("card").textValue());
            var second = get(root + directory.get(1).get("card").textValue());
            assertThat(get(root + CARD)).isEqualTo(first);
            String echo = endpoint(first, root + "/echo");
            String stream = endpoint(second, root + "/services/stream");
            assertThat(first.at("/capabilities/streaming").booleanValue()).isFalse();
            assertThat(first.at("/capabilities/pushNotifications").booleanValue()).isFalse();
            assertThat(first.at("/skills/0/tags")).isEqualTo(json.valueToTree(List.of("echo")));
            assertThat(first.at("/skills/1/tags")).isEqualTo(json.valueToTree(List.of("health")));
            assertThat(second.at("/capabilities/streaming").booleanValue()).isTrue();
            assertThat(second.at("/capabilities/pushNotifications").booleanValue()).isTrue();
            assertThat(second.at("/securitySchemes/bearer/httpAuthSecurityScheme/scheme").asText()).isEqualTo("bearer");

            var text = rpc(echo, "SendMessage", message("hello world"), null);
            assertThat(text.at("/result/message/parts/0/text").asText()).isEqualTo("hello world");
            assertThat(rpc(echo, "SendMessage", message("{\"skill\":\"ping\"}"), null)
                .at("/result/message/parts/0/text").asText()).isEqualTo("pong");
            assertThat(rpc(echo, "SendMessage", message("{\"skill\":\"missing\"}"), null)
                .at("/result/task/status/state").asText()).isEqualTo("TASK_STATE_FAILED");
            assertThat(rpc(stream, "SendMessage", message("ambiguous"), "key")
                .at("/result/task/status/state").asText()).isEqualTo("TASK_STATE_FAILED");
            var unauthorized = post(stream, "SendStreamingMessage", message("{\"skill\":\"read\"}"), null);
            assertThat(unauthorized.statusCode()).isEqualTo(401);
            assertThat(json.readTree(unauthorized.body()).get("id").longValue()).isEqualTo(ID);

            var sse = post(stream, "SendStreamingMessage", message("{\"skill\":\"read\"}"), "key");
            assertThat(sse.statusCode()).isEqualTo(200);
            assertThat(sse.headers().firstValue("content-type")).hasValue("text/event-stream");
            var events = new ArrayList<JsonNode>();
            for (String line : sse.body().lines().filter(line -> line.startsWith("data: ")).toList()) {
                var event = json.readTree(line.substring(6));
                assertThat(event.get("id").longValue()).isEqualTo(ID);
                events.add(event.get("result"));
            }
            String taskId = events.get(0).at("/task/id").textValue();
            assertThat(taskId).isNotBlank();
            assertThat(events.stream().map(event -> event.at("/statusUpdate/status/message/parts/0/text").textValue())
                .filter(java.util.Objects::nonNull)).containsExactly("one", "two");
            assertThat(events.get(events.size() - 1).at("/statusUpdate/status/state").asText()).isEqualTo("TASK_STATE_COMPLETED");
            assertThat(rpc(stream, "GetTask", Map.of("id", taskId), "key").at("/result/id").asText()).isEqualTo(taskId);
            assertThat(rpc(echo, "GetTask", Map.of("id", taskId), null).has("error")).isTrue();
            var pushList = rpc(stream, "ListTaskPushNotificationConfigs", Map.of("taskId", taskId), "key");
            assertThat(pushList.has("result")).as(pushList.toString()).isTrue();
            assertThat(pushList.at("/result/configs")).isEmpty();
        }
        assertThat(closed.get()).isEqualTo(2);
    }

    @Test
    void rejectsAnAnonymousAuthenticatedProfileAtMountStartup() {
        var invalid = Agent.builder().name("Invalid").description("Requires identity")
            .runtimeOptions(RuntimeOptions.authenticated()).build();
        try (var router = new AgentRouter().mount("/invalid", invalid)) {
            assertThatThrownBy(() -> router.start("127.0.0.1", 0)).hasMessageContaining("identified authentication");
        }
    }

    private JsonNode get(String url) throws Exception {
        var request = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(5)).build();
        var response = http.send(request, HttpResponse.BodyHandlers.ofString());
        assertThat(response.statusCode()).isEqualTo(200);
        return json.readTree(response.body());
    }

    private String endpoint(JsonNode card, String expected) {
        assertThat(card.path("supportedInterfaces").size()).isEqualTo(1);
        assertThat(card.at("/supportedInterfaces/0/protocolBinding").textValue()).isEqualTo("JSONRPC");
        String url = card.at("/supportedInterfaces/0/url").textValue();
        assertThat(url).isEqualTo(expected);
        return url;
    }

    private Map<String, Object> message(String text) {
        return Map.of("message", Map.of("messageId", UUID.randomUUID().toString(), "role", "ROLE_USER",
            "parts", List.of(Map.of("text", text))));
    }

    private JsonNode rpc(String url, String method, Object params, String key) throws Exception {
        var response = post(url, method, params, key);
        assertThat(response.statusCode()).isEqualTo(200);
        var envelope = json.readTree(response.body());
        assertThat(envelope.get("id").longValue()).isEqualTo(ID);
        return envelope;
    }

    private HttpResponse<String> post(String url, String method, Object params, String key) throws Exception {
        String body = json.writeValueAsString(Map.of("jsonrpc", "2.0", "id", ID, "method", method, "params", params));
        var request = HttpRequest.newBuilder(URI.create(url)).timeout(Duration.ofSeconds(10))
            .header("Content-Type", "application/json").header("A2A-Version", "1.0")
            .POST(HttpRequest.BodyPublishers.ofString(body));
        if (key != null) request.header("Authorization", "Bearer " + key);
        return http.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }
}
