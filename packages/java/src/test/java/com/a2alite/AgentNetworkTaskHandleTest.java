package com.a2alite;

import com.fasterxml.jackson.databind.ObjectMapper;
import io.javalin.Javalin;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AgentNetworkTaskHandleTest {

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

    // ---- callRemoteSkillWithHandle ------------------------------------------

    @Test
    void callRemoteSkillWithHandleReturnsTaskHandle() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("SendMessage");
            assertThat(body.path("params").path("message").path("role").asText())
                .isEqualTo("ROLE_USER");
            assertThat(ctx.header("A2A-Version")).isEqualTo("1.0");

            var response = Map.of(
                "jsonrpc", "2.0",
                "id", "req-1",
                "result", Map.of(
                    "task", Map.of(
                        "id", "task-abc-123",
                        "contextId", "ctx-1",
                        "status", Map.of("state", "TASK_STATE_COMPLETED"),
                        "artifacts", List.of(Map.of(
                            "artifactId", "a-1",
                            "parts", List.of(Map.of("text", "{\"answer\":42}"))
                        ))
                    )
                )
            );
            ctx.json(response);
        });

        var network = new AgentNetwork();
        var handle = network.callRemoteSkillWithHandle(
            "http://localhost:" + port, "mySkill", Map.of("q", "test"), 10
        );

        assertThat(handle).isNotNull();
        assertThat(handle.getTaskId()).isEqualTo("task-abc-123");
        assertThat(handle.getAgentUrl()).isEqualTo("http://localhost:" + port);
        assertThat(handle.getResult()).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) handle.getResult();
        assertThat(resultMap.get("answer")).isEqualTo(42);
    }

    @Test
    void callRemoteSkillWithHandleMessageResponse() throws Exception {
        app.post("/", ctx -> {
            var response = Map.of(
                "jsonrpc", "2.0",
                "id", "req-2",
                "result", Map.of(
                    "message", Map.of(
                        "role", "ROLE_AGENT",
                        "messageId", "m-1",
                        "taskId", "task-from-message",
                        "parts", List.of(Map.of("text", "\"plain result\""))
                    )
                )
            );
            ctx.json(response);
        });

        var network = new AgentNetwork();
        var handle = network.callRemoteSkillWithHandle(
            "http://localhost:" + port, "skill", Map.of(), 10
        );

        assertThat(handle.getTaskId()).isEqualTo("task-from-message");
        assertThat(handle.getResult()).isEqualTo("plain result");
    }

    @Test
    void callRemoteSkillWithHandleNullTaskId() throws Exception {
        app.post("/", ctx -> {
            var response = Map.of(
                "jsonrpc", "2.0",
                "id", "req-2b",
                "result", Map.of(
                    "message", Map.of(
                        "role", "ROLE_AGENT",
                        "messageId", "m-1",
                        "parts", List.of(Map.of("text", "\"plain result\""))
                    )
                )
            );
            ctx.json(response);
        });

        var network = new AgentNetwork();
        var handle = network.callRemoteSkillWithHandle(
            "http://localhost:" + port, "skill", Map.of(), 10
        );

        assertThat(handle.getTaskId()).isNull();
        assertThat(handle.getResult()).isEqualTo("plain result");
    }

    // ---- callWithHandle -----------------------------------------------------

    @Test
    void callWithHandleResolvesNameAndReturnsTaskHandle() throws Exception {
        app.post("/", ctx -> {
            var response = Map.of(
                "jsonrpc", "2.0",
                "id", "req-3",
                "result", Map.of(
                    "task", Map.of(
                        "id", "task-xyz",
                        "contextId", "ctx-2",
                        "status", Map.of(
                            "state", "TASK_STATE_COMPLETED",
                            "message", Map.of(
                                "role", "ROLE_AGENT",
                                "messageId", "m-2",
                                "parts", List.of(Map.of("text", "\"done\""))
                            )
                        )
                    )
                )
            );
            ctx.json(response);
        });

        var network = new AgentNetwork();
        network.add("myAgent", "http://localhost:" + port);

        var handle = network.callWithHandle("myAgent", "doStuff", Map.of(), 10);

        assertThat(handle.getTaskId()).isEqualTo("task-xyz");
        assertThat(handle.getResult()).isEqualTo("done");
        assertThat(handle.getAgentUrl()).isEqualTo("http://localhost:" + port);
    }

    @Test
    void callWithHandleThrowsForUnknownAgent() {
        var network = new AgentNetwork();

        assertThatThrownBy(() ->
            network.callWithHandle("unknown", "skill", Map.of(), 10)
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("unknown");
    }

    // ---- getRemoteTask ------------------------------------------------------

    @Test
    void getRemoteTaskSendsCorrectRequest() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("GetTask");
            assertThat(body.path("params").path("id").asText()).isEqualTo("task-99");
            assertThat(ctx.header("A2A-Version")).isEqualTo("1.0");

            var response = Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-99",
                    "contextId", "ctx-99",
                    "status", Map.of("state", "TASK_STATE_COMPLETED"),
                    "artifacts", List.of(Map.of(
                        "artifactId", "a-99",
                        "parts", List.of(Map.of("text", "{\"status\":\"done\"}"))
                    ))
                )
            );
            ctx.json(response);
        });

        var network = new AgentNetwork();
        var result = network.getRemoteTask("http://localhost:" + port, "task-99", 10);

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("status")).isEqualTo("done");
    }

    // ---- cancelRemoteTask ---------------------------------------------------

    @Test
    void cancelRemoteTaskSendsCorrectRequest() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("CancelTask");
            assertThat(body.path("params").path("id").asText()).isEqualTo("task-42");

            var response = Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-42",
                    "contextId", "ctx-42",
                    "status", Map.of("state", "TASK_STATE_CANCELED"),
                    "artifacts", List.of(Map.of(
                        "artifactId", "a-42",
                        "parts", List.of(Map.of("text", "{\"canceled\":true}"))
                    ))
                )
            );
            ctx.json(response);
        });

        var network = new AgentNetwork();
        var result = network.cancelRemoteTask("http://localhost:" + port, "task-42", 10);

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("canceled")).isEqualTo(true);
    }

    // ---- Error handling -----------------------------------------------------

    @Test
    void callRemoteSkillWithHandleThrowsOnHttpError() {
        app.post("/", ctx -> {
            ctx.status(500);
            ctx.result("Internal Server Error");
        });

        var network = new AgentNetwork();
        assertThatThrownBy(() ->
            network.callRemoteSkillWithHandle(
                "http://localhost:" + port, "skill", Map.of(), 5
            )
        ).hasMessageContaining("HTTP 500");
    }

    @Test
    void callRemoteSkillThrowsOnJsonRpcError() {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "error", Map.of("code", -32601, "message", "Method not found")
            ));
        });

        var network = new AgentNetwork();
        assertThatThrownBy(() ->
            network.callRemoteSkill("http://localhost:" + port, "skill", Map.of(), 5)
        ).hasMessageContaining("Method not found");
    }

    // ---- TaskHandle.getStatus / cancel --------------------------------------

    @Test
    void testTaskHandle_getStatus() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("GetTask");
            assertThat(body.path("params").path("id").asText()).isEqualTo("task-handle-1");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-handle-1",
                    "contextId", "ctx-h1",
                    "status", Map.of("state", "TASK_STATE_COMPLETED"),
                    "artifacts", List.of(Map.of(
                        "artifactId", "a-h1",
                        "parts", List.of(Map.of("text", "{\"progress\":100}"))
                    ))
                )
            ));
        });

        var network = new AgentNetwork();
        var handle = new TaskHandle("task-handle-1", "initial", "http://localhost:" + port, network);

        var status = handle.getStatus();

        assertThat(status).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var statusMap = (Map<String, Object>) status;
        assertThat(statusMap.get("progress")).isEqualTo(100);
    }

    @Test
    void testTaskHandle_cancel() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("CancelTask");
            assertThat(body.path("params").path("id").asText()).isEqualTo("task-handle-2");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-handle-2",
                    "contextId", "ctx-h2",
                    "status", Map.of("state", "TASK_STATE_CANCELED"),
                    "artifacts", List.of(Map.of(
                        "artifactId", "a-h2",
                        "parts", List.of(Map.of("text", "{\"canceled\":true}"))
                    ))
                )
            ));
        });

        var network = new AgentNetwork();
        var handle = new TaskHandle("task-handle-2", "initial", "http://localhost:" + port, network);

        var result = handle.cancel();

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("canceled")).isEqualTo(true);
    }

    @Test
    void testTaskHandle_getStatus_withoutNetwork() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-no-net",
                    "contextId", "ctx-nn",
                    "status", Map.of("state", "TASK_STATE_COMPLETED"),
                    "artifacts", List.of(Map.of(
                        "artifactId", "a-nn",
                        "parts", List.of(Map.of("text", "{\"fallback\":true}"))
                    ))
                )
            ));
        });

        // TaskHandle created without network reference — uses fallback AgentNetwork
        var handle = new TaskHandle("task-no-net", "initial", "http://localhost:" + port);

        var status = handle.getStatus();

        assertThat(status).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var statusMap = (Map<String, Object>) status;
        assertThat(statusMap.get("fallback")).isEqualTo(true);
    }

    // ---- AgentNetwork.getTask / cancelTask ----------------------------------

    @Test
    void testAgentNetwork_getTask() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("GetTask");
            assertThat(body.path("params").path("id").asText()).isEqualTo("task-named-1");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-named-1",
                    "contextId", "ctx-n1",
                    "status", Map.of("state", "TASK_STATE_COMPLETED"),
                    "artifacts", List.of(Map.of(
                        "artifactId", "a-n1",
                        "parts", List.of(Map.of("text", "{\"found\":true}"))
                    ))
                )
            ));
        });

        var network = new AgentNetwork();
        network.add("myAgent", "http://localhost:" + port);

        var result = network.getTask("myAgent", "task-named-1");

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("found")).isEqualTo(true);
    }

    @Test
    void testAgentNetwork_cancelTask() throws Exception {
        app.post("/", ctx -> {
            var body = mapper.readTree(ctx.body());
            assertThat(body.get("method").asText()).isEqualTo("CancelTask");
            assertThat(body.path("params").path("id").asText()).isEqualTo("task-named-2");

            ctx.json(Map.of(
                "jsonrpc", "2.0",
                "id", body.get("id").asText(),
                "result", Map.of(
                    "id", "task-named-2",
                    "contextId", "ctx-n2",
                    "status", Map.of("state", "TASK_STATE_CANCELED"),
                    "artifacts", List.of(Map.of(
                        "artifactId", "a-n2",
                        "parts", List.of(Map.of("text", "{\"canceled\":true}"))
                    ))
                )
            ));
        });

        var network = new AgentNetwork();
        network.add("myAgent", "http://localhost:" + port);

        var result = network.cancelTask("myAgent", "task-named-2");

        assertThat(result).isInstanceOf(Map.class);
        @SuppressWarnings("unchecked")
        var resultMap = (Map<String, Object>) result;
        assertThat(resultMap.get("canceled")).isEqualTo(true);
    }

    @Test
    void testAgentNetwork_getTask_unknownName() {
        var network = new AgentNetwork();

        assertThatThrownBy(() ->
            network.getTask("nonexistent", "task-1")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("nonexistent");
    }
}
