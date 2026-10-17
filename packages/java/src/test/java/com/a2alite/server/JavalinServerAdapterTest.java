package com.a2alite.server;

import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.assertj.core.api.Assertions.assertThat;

class JavalinServerAdapterTest {

    @Test
    void servedCardShouldAdvertiseImplementedStreaming() throws Exception {
        var agent = Agent.builder().name("StreamingBot").description("SDK streaming").build();
        agent.skill("stream", SkillConfig.withStreaming(), params -> "Hello");
        int port;
        try (var socket = new ServerSocket(0)) {
            port = socket.getLocalPort();
        }

        var adapter = new JavalinServerAdapter();
        try {
            adapter.start(agent, "127.0.0.1", port);
            var request = HttpRequest.newBuilder()
                .uri(URI.create("http://127.0.0.1:" + port + "/.well-known/agent-card.json"))
                .timeout(Duration.ofSeconds(5))
                .build();
            var response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());

            assertThat(response.statusCode()).isEqualTo(200);
            var card = new ObjectMapper().readTree(response.body());
            assertThat(card.path("supportedInterfaces").size()).isEqualTo(1);
            assertThat(card.path("supportedInterfaces").get(0).path("protocolBinding").asText())
                .isEqualTo("JSONRPC");
            assertThat(card.path("capabilities").path("streaming").asBoolean()).isTrue();
            assertThat(agent.buildAgentCard("localhost", port).capabilities().streaming()).isTrue();
            assertThat(agent.buildAgentCardJson("localhost", port).path("capabilities")
                .path("streaming").asBoolean()).isTrue();
        } finally {
            adapter.stop();
        }
    }

    @Test
    void shouldInstantiateJavalinServerAdapter() {
        var adapter = new JavalinServerAdapter();
        assertThat(adapter).isNotNull();
    }

    @Test
    void shouldInstantiateJavalinServerAdapterWithCorsOrigins() {
        var adapter = new JavalinServerAdapter(List.of("https://example.com"));
        assertThat(adapter).isNotNull();
    }

    @Test
    void createIfAvailableShouldReturnAdapterWhenJavalinIsOnClasspath() {
        // Javalin is on the test classpath (testImplementation dependency)
        var adapter = JavalinServerAdapter.createIfAvailable();
        assertThat(adapter).isNotNull();
    }

    @Test
    void createIfAvailableWithCorsOriginsShouldReturnAdapterWhenJavalinIsOnClasspath() {
        var adapter = JavalinServerAdapter.createIfAvailable(List.of("https://example.com"));
        assertThat(adapter).isNotNull();
    }

    @Test
    void shouldSetServerAdapterViaAgentBuilder() {
        var adapter = new JavalinServerAdapter();

        var agent = Agent.builder()
            .name("AdapterTestBot")
            .description("Tests serverAdapter builder method")
            .serverAdapter(adapter)
            .build();

        // The agent should build successfully — we can't easily inspect the private
        // field, but we can verify nothing threw during construction.
        assertThat(agent).isNotNull();
        assertThat(agent.getName()).isEqualTo("AdapterTestBot");
    }

    @Test
    void shouldAcceptCustomServerAdapterViaBuilder() {
        AtomicBoolean startCalled = new AtomicBoolean(false);
        AtomicBoolean stopCalled = new AtomicBoolean(false);

        // Stub adapter — records calls without starting a real server
        ServerAdapter stub = new ServerAdapter() {
            @Override
            public void start(Agent agent, String host, int port) {
                startCalled.set(true);
            }

            @Override
            public void stop() {
                stopCalled.set(true);
            }
        };

        var agent = Agent.builder()
            .name("StubBot")
            .description("Uses a stub server adapter")
            .serverAdapter(stub)
            .build();

        assertThat(agent).isNotNull();

        // Invoke the adapter directly to confirm the stub works
        stub.start(agent, "localhost", 9999);
        stub.stop();

        assertThat(startCalled).isTrue();
        assertThat(stopCalled).isTrue();
    }

    @Test
    void customAdapterShouldBeInvokedByAgentRun() {
        AtomicBoolean started = new AtomicBoolean(false);

        ServerAdapter stub = new ServerAdapter() {
            @Override
            public void start(Agent agent, String host, int port) {
                started.set(true);
            }

            @Override
            public void stop() {
            }
        };

        var agent = Agent.builder()
            .name("RunBot")
            .description("Verifies adapter is called by agent.run()")
            .serverAdapter(stub)
            .build();

        agent.run(9998);

        assertThat(started).isTrue();
    }
}
