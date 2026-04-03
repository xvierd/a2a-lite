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
                "data: {\"artifact\":{\"parts\":[{\"kind\":\"text\",\"text\":\"Hello\"}]},\"final\":false}\n\n" +
                "data: {\"artifact\":{\"parts\":[{\"kind\":\"text\",\"text\":\" beautiful\"}]},\"final\":false}\n\n" +
                "data: {\"artifact\":{\"parts\":[{\"kind\":\"text\",\"text\":\" World\"}]},\"final\":false}\n\n" +
                "data: {\"status\":{\"state\":\"completed\"},\"final\":true}\n\n"
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
    void testStreamRemoteSkill_stopsAtFinal() {
        app.post("/", ctx -> {
            ctx.contentType("text/event-stream");
            ctx.result(
                "data: {\"artifact\":{\"parts\":[{\"kind\":\"text\",\"text\":\"chunk1\"}]},\"final\":false}\n\n" +
                "data: {\"status\":{\"state\":\"completed\"},\"final\":true}\n\n" +
                "data: {\"artifact\":{\"parts\":[{\"kind\":\"text\",\"text\":\"should-not-appear\"}]},\"final\":false}\n\n"
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
                "data: {\"artifact\":{\"parts\":[{\"kind\":\"text\",\"text\":\"partial\"}]},\"final\":false}\n\n" +
                "data: {\"status\":{\"state\":\"failed\"},\"final\":true}\n\n"
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
                "data: {\"artifact\":{\"parts\":[{\"kind\":\"text\",\"text\":\"resolved\"}]},\"final\":false}\n\n" +
                "data: {\"status\":{\"state\":\"completed\"},\"final\":true}\n\n"
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
    void testStreamRemoteSkill_handlesTypeField() {
        app.post("/", ctx -> {
            ctx.contentType("text/event-stream");
            ctx.result(
                "data: {\"artifact\":{\"parts\":[{\"type\":\"text\",\"text\":\"via-type\"}]},\"final\":false}\n\n" +
                "data: {\"status\":{\"state\":\"completed\"},\"final\":true}\n\n"
            );
        });

        var network = new AgentNetwork();
        var result = network.streamRemoteSkill(
            "http://localhost:" + port, "skill", Map.of(), 10);

        var chunks = new ArrayList<String>();
        for (Object chunk : result) {
            chunks.add((String) chunk);
        }

        assertThat(chunks).containsExactly("via-type");
    }
}
