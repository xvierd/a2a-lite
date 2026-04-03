package com.a2alite;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.javalin.Javalin;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class PerTaskPushTest {

    private Javalin app;
    private int port;
    private final ObjectMapper mapper = new ObjectMapper();

    @BeforeEach
    void setUp() {
        app = Javalin.create().start(0);
        port = app.port();
    }

    @AfterEach
    void tearDown() {
        if (app != null) {
            app.stop();
        }
    }

    // ---- AgentNetwork.setTaskPushNotification --------------------------------

    @Test
    void setTaskPushNotificationSendsCorrectBody() throws Exception {
        var receivedBody = new AtomicReference<String>();

        app.post("/", ctx -> {
            receivedBody.set(ctx.body());
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("tasks/pushNotification/set");
            assertThat(body.path("params").path("id").asText()).isEqualTo("task-push-1");
            assertThat(body.path("params").path("pushNotificationConfig").path("url").asText())
                .isEqualTo("http://my-webhook.com/hook");
            assertThat(body.path("params").path("pushNotificationConfig").path("token").asText())
                .isEqualTo("secret-token");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-push-1",
                    "pushNotificationConfig", Map.of(
                        "url", "http://my-webhook.com/hook",
                        "token", "secret-token"
                    )
                )
            ));
        });

        var network = new AgentNetwork();
        var result = network.setTaskPushNotification(
            "http://localhost:" + port, "task-push-1",
            "http://my-webhook.com/hook", "secret-token", 10
        );

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("id")).isEqualTo("task-push-1");
        assertThat(receivedBody.get()).isNotNull();
    }

    @Test
    void setTaskPushNotificationWithoutToken() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            var configNode = body.path("params").path("pushNotificationConfig");
            assertThat(configNode.has("token")).isFalse();

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-push-2",
                    "pushNotificationConfig", Map.of("url", "http://hook.com")
                )
            ));
        });

        var network = new AgentNetwork();
        var result = network.setTaskPushNotification(
            "http://localhost:" + port, "task-push-2", "http://hook.com"
        );

        assertThat(result).isNotNull();
    }

    // ---- AgentNetwork.getTaskPushNotification --------------------------------

    @Test
    void getTaskPushNotificationRetrievesConfig() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("tasks/pushNotification/get");
            assertThat(body.path("params").path("id").asText()).isEqualTo("task-push-3");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-push-3",
                    "pushNotificationConfig", Map.of(
                        "url", "http://hook.com/callback"
                    )
                )
            ));
        });

        var network = new AgentNetwork();
        var result = network.getTaskPushNotification(
            "http://localhost:" + port, "task-push-3", 10
        );

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("id")).isEqualTo("task-push-3");
    }

    // ---- AgentNetwork.deleteTaskPushNotification -----------------------------

    @Test
    void deleteTaskPushNotificationSendsDelete() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("tasks/pushNotification/delete");
            assertThat(body.path("params").path("id").asText()).isEqualTo("task-push-4");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-push-4",
                    "deleted", true
                )
            ));
        });

        var network = new AgentNetwork();
        var result = network.deleteTaskPushNotification(
            "http://localhost:" + port, "task-push-4", 10
        );

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("deleted")).isEqualTo(true);
    }

    // ---- TaskHandle.subscribe / unsubscribe ----------------------------------

    @Test
    void taskHandleSubscribe() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("tasks/pushNotification/set");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-sub-1",
                    "pushNotificationConfig", Map.of("url", "http://hook.com")
                )
            ));
        });

        var network = new AgentNetwork();
        var handle = new TaskHandle("task-sub-1", "initial", "http://localhost:" + port, network);

        var result = handle.subscribe("http://hook.com");

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("id")).isEqualTo("task-sub-1");
    }

    @Test
    void taskHandleUnsubscribe() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("tasks/pushNotification/delete");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-unsub-1",
                    "deleted", true
                )
            ));
        });

        var network = new AgentNetwork();
        var handle = new TaskHandle("task-unsub-1", "initial", "http://localhost:" + port, network);

        var result = handle.unsubscribe();

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("deleted")).isEqualTo(true);
    }

    @Test
    void taskHandleGetPushConfig() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("tasks/pushNotification/get");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-cfg-1",
                    "pushNotificationConfig", Map.of("url", "http://hook.com")
                )
            ));
        });

        var network = new AgentNetwork();
        var handle = new TaskHandle("task-cfg-1", "initial", "http://localhost:" + port, network);

        var result = handle.getPushConfig();

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("id")).isEqualTo("task-cfg-1");
    }
}
