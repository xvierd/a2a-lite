package com.a2alite;

import com.a2alite.errors.RemoteAgentException;
import com.a2alite.streaming.StreamingHandler;
import io.javalin.Javalin;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AgentNetworkStreamingTest {

    private Javalin app;
    private int port;

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

    @Test
    void testStreamRemoteSkill_yieldsChunks() {
        app.post("/", ctx -> {
            ctx.contentType("text/event-stream");
            ctx.result(
                "data: {\"result\":{\"artifactUpdate\":{\"artifact\":{\"artifactId\":\"a1\",\"parts\":[{\"text\":\"Hello\"}]}}}}\n\n" +
                "data: {\"result\":{\"artifactUpdate\":{\"artifact\":{\"artifactId\":\"a1\",\"parts\":[{\"text\":\" beautiful\"}]}}}}\n\n" +
                "data: {\"result\":{\"artifactUpdate\":{\"artifact\":{\"artifactId\":\"a1\",\"parts\":[{\"text\":\" World\"}]}}}}\n\n" +
                "data: {\"result\":{\"statusUpdate\":{\"taskId\":\"t1\",\"contextId\":\"c1\",\"status\":{\"state\":\"TASK_STATE_COMPLETED\"}}}}\n\n"
            );
        });

        var network = new AgentNetwork();
        var result = network.streamRemoteSkill(
            "http://localhost:" + port, "mySkill", Map.of("q", "test"), 10);

        var chunks = new ArrayList<String>();
        for (Object chunk : result) {
            chunks.add((String) chunk);
        }

        assertThat(chunks).containsExactly("Hello", " beautiful", " World");
    }

    @Test
    void testStreamRemoteSkill_yieldsStatusMessageChunks() {
        app.post("/", ctx -> {
            ctx.contentType("text/event-stream");
            ctx.result(
                "data: {\"result\":{\"task\":{\"id\":\"t1\",\"contextId\":\"c1\",\"status\":{\"state\":\"TASK_STATE_SUBMITTED\"}}}}\n\n" +
                "data: {\"result\":{\"statusUpdate\":{\"taskId\":\"t1\",\"contextId\":\"c1\",\"status\":{\"state\":\"TASK_STATE_WORKING\",\"message\":{\"role\":\"ROLE_AGENT\",\"messageId\":\"m1\",\"parts\":[{\"text\":\"chunk-a\"}]}}}}}\n\n" +
                "data: {\"result\":{\"statusUpdate\":{\"taskId\":\"t1\",\"contextId\":\"c1\",\"status\":{\"state\":\"TASK_STATE_WORKING\",\"message\":{\"role\":\"ROLE_AGENT\",\"messageId\":\"m2\",\"parts\":[{\"text\":\"chunk-b\"}]}}}}}\n\n" +
                "data: {\"result\":{\"statusUpdate\":{\"taskId\":\"t1\",\"contextId\":\"c1\",\"status\":{\"state\":\"TASK_STATE_COMPLETED\"}}}}\n\n"
            );
        });

        var network = new AgentNetwork();
        var result = network.streamRemoteSkill(
            "http://localhost:" + port, "mySkill", Map.of("q", "test"), 10);

        var chunks = new ArrayList<String>();
        for (Object chunk : result) {
            chunks.add((String) chunk);
        }

        assertThat(chunks).containsExactly("chunk-a", "chunk-b");
    }

    @Test
    void testStreamRemoteSkill_stopsAtTerminalState() {
        app.post("/", ctx -> {
            ctx.contentType("text/event-stream");
            ctx.result(
                "data: {\"result\":{\"artifactUpdate\":{\"artifact\":{\"artifactId\":\"a1\",\"parts\":[{\"text\":\"chunk1\"}]}}}}\n\n" +
                "data: {\"result\":{\"statusUpdate\":{\"taskId\":\"t1\",\"contextId\":\"c1\",\"status\":{\"state\":\"TASK_STATE_COMPLETED\"}}}}\n\n" +
                "data: {\"result\":{\"artifactUpdate\":{\"artifact\":{\"artifactId\":\"a1\",\"parts\":[{\"text\":\"should-not-appear\"}]}}}}\n\n"
            );
        });

        var network = new AgentNetwork();
        var result = network.streamRemoteSkill(
            "http://localhost:" + port, "skill", Map.of(), 10);

        var chunks = new ArrayList<String>();
        for (Object chunk : result) {
            chunks.add((String) chunk);
        }

        assertThat(chunks).containsExactly("chunk1");
    }

    @Test
    void testStreamRemoteSkill_throwsOnFailed() {
        app.post("/", ctx -> {
            ctx.contentType("text/event-stream");
            ctx.result(
                "data: {\"result\":{\"artifactUpdate\":{\"artifact\":{\"artifactId\":\"a1\",\"parts\":[{\"text\":\"partial\"}]}}}}\n\n" +
                "data: {\"result\":{\"statusUpdate\":{\"taskId\":\"t1\",\"contextId\":\"c1\",\"status\":{\"state\":\"TASK_STATE_FAILED\"}}}}\n\n"
            );
        });

        var network = new AgentNetwork();
        var result = network.streamRemoteSkill(
            "http://localhost:" + port, "skill", Map.of(), 10);

        assertThatThrownBy(() -> {
            for (Object chunk : result) {
                // consume
            }
        }).hasCauseInstanceOf(RemoteAgentException.class);
    }

    @Test
    void testStream_resolvesName() {
        app.post("/", ctx -> {
            ctx.contentType("text/event-stream");
            ctx.result(
                "data: {\"result\":{\"artifactUpdate\":{\"artifact\":{\"artifactId\":\"a1\",\"parts\":[{\"text\":\"resolved\"}]}}}}\n\n" +
                "data: {\"result\":{\"statusUpdate\":{\"taskId\":\"t1\",\"contextId\":\"c1\",\"status\":{\"state\":\"TASK_STATE_COMPLETED\"}}}}\n\n"
            );
        });

        var network = new AgentNetwork();
        network.add("agent", "http://localhost:" + port);

        var result = network.stream("agent", "skill", Map.of());

        var chunks = new ArrayList<String>();
        for (Object chunk : result) {
            chunks.add((String) chunk);
        }

        assertThat(chunks).containsExactly("resolved");
    }

    @Test
    void testStream_throwsForUnknownAgent() {
        var network = new AgentNetwork();

        assertThatThrownBy(() ->
            network.stream("unknown", "skill", Map.of())
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessageContaining("unknown");
    }

    @Test
    void testStreamRemoteSkill_handlesMessageEvent() {
        app.post("/", ctx -> {
            ctx.contentType("text/event-stream");
            ctx.result(
                "data: {\"result\":{\"message\":{\"role\":\"ROLE_AGENT\",\"messageId\":\"m1\",\"parts\":[{\"text\":\"via-message\"}]}}}\n\n"
            );
        });

        var network = new AgentNetwork();
        var result = network.streamRemoteSkill(
            "http://localhost:" + port, "skill", Map.of(), 10);

        var chunks = new ArrayList<String>();
        for (Object chunk : result) {
            chunks.add((String) chunk);
        }

        assertThat(chunks).containsExactly("via-message");
    }

    @Test
    void testStreamRemoteSkill_sendsStreamingRequest() {
        var received = new java.util.concurrent.atomic.AtomicReference<String>();
        var versionHeader = new java.util.concurrent.atomic.AtomicReference<String>();
        app.post("/", ctx -> {
            received.set(ctx.body());
            versionHeader.set(ctx.header("A2A-Version"));
            ctx.contentType("text/event-stream");
            ctx.result(
                "data: {\"result\":{\"statusUpdate\":{\"taskId\":\"t1\",\"contextId\":\"c1\",\"status\":{\"state\":\"TASK_STATE_COMPLETED\"}}}}\n\n"
            );
        });

        var network = new AgentNetwork();
        var result = network.streamRemoteSkill(
            "http://localhost:" + port, "skill", Map.of(), 10);
        for (Object chunk : result) {
            // consume
        }

        assertThat(versionHeader.get()).isEqualTo("1.0");
        assertThat(received.get()).contains("\"method\":\"SendStreamingMessage\"");
        assertThat(received.get()).contains("\"role\":\"ROLE_USER\"");
    }
}
