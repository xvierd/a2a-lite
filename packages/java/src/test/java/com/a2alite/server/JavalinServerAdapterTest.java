package com.a2alite.server;

import com.a2alite.Agent;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.assertj.core.api.Assertions.assertThat;

class JavalinServerAdapterTest {

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
