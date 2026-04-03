package com.a2alite;

import io.javalin.Javalin;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class AgentCardInfoTest {

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

    // ---- AgentCardInfo fields -----------------------------------------------

    @Test
    void testAgentCardInfoFields() {
        var skills = List.of(
            Map.<String, Object>of("id", "greet", "name", "greet", "description", "Greets user")
        );
        var raw = Map.<String, Object>of("name", "TestAgent", "custom", "field");

        var card = new AgentCardInfo(
            "TestAgent", "A test agent", "http://localhost:8787",
            "1.0.0", skills, true, false, raw
        );

        assertThat(card.getName()).isEqualTo("TestAgent");
        assertThat(card.getDescription()).isEqualTo("A test agent");
        assertThat(card.getUrl()).isEqualTo("http://localhost:8787");
        assertThat(card.getVersion()).isEqualTo("1.0.0");
        assertThat(card.getSkills()).hasSize(1);
        assertThat(card.isSupportsStreaming()).isTrue();
        assertThat(card.isSupportsPush()).isFalse();
        assertThat(card.getRaw()).containsKey("custom");
    }

    @Test
    void testAgentCardInfoNullSkillsAndRaw() {
        var card = new AgentCardInfo("Agent", "desc", "http://url", "1.0", null, false, false, null);

        assertThat(card.getSkills()).isEmpty();
        assertThat(card.getRaw()).isEmpty();
    }

    @Test
    void testAgentCardInfoToString() {
        var card = new AgentCardInfo(
            "Bot", "desc", "http://localhost", "1.0",
            List.of(Map.of("id", "s1"), Map.of("id", "s2")),
            false, false, Map.of()
        );
        assertThat(card.toString()).contains("Bot").contains("skills=2");
    }

    // ---- discoverAgent via mock HTTP ----------------------------------------

    @Test
    void discoverAgentParsesCardFromServer() throws Exception {
        app.get("/.well-known/agent.json", ctx -> {
            ctx.json(Map.of(
                "name", "RemoteBot",
                "description", "Remote agent",
                "url", "http://localhost:" + port,
                "version", "2.0.0",
                "capabilities", Map.of("streaming", true, "pushNotifications", false),
                "skills", List.of(
                    Map.of("id", "echo", "name", "echo", "description", "Echo skill")
                )
            ));
        });

        var network = new AgentNetwork();
        var card = network.discoverAgent("http://localhost:" + port, 10);

        assertThat(card.getName()).isEqualTo("RemoteBot");
        assertThat(card.getDescription()).isEqualTo("Remote agent");
        assertThat(card.getVersion()).isEqualTo("2.0.0");
        assertThat(card.isSupportsStreaming()).isTrue();
        assertThat(card.isSupportsPush()).isFalse();
        assertThat(card.getSkills()).hasSize(1);
        assertThat(card.getSkills().get(0).get("id")).isEqualTo("echo");
        assertThat(card.getRaw()).containsKey("name");
    }

    @Test
    void discoverAgentThrowsOnHttpError() {
        app.get("/.well-known/agent.json", ctx -> ctx.status(404));

        var network = new AgentNetwork();
        assertThatThrownBy(() ->
            network.discoverAgent("http://localhost:" + port, 5)
        ).hasMessageContaining("HTTP 404");
    }

    @Test
    void discoverAgentStripsTrailingSlash() throws Exception {
        app.get("/.well-known/agent.json", ctx -> {
            ctx.json(Map.of(
                "name", "Agent",
                "description", "desc",
                "url", "http://localhost:" + port,
                "version", "1.0"
            ));
        });

        var network = new AgentNetwork();
        var card = network.discoverAgent("http://localhost:" + port + "/", 10);
        assertThat(card.getName()).isEqualTo("Agent");
    }

    // ---- add with autoDiscover ----------------------------------------------

    @Test
    void addWithAutoDiscoverCachesCard() throws Exception {
        app.get("/.well-known/agent.json", ctx -> {
            ctx.json(Map.of(
                "name", "AutoBot",
                "description", "Auto-discovered",
                "url", "http://localhost:" + port,
                "version", "1.0"
            ));
        });

        var network = new AgentNetwork();
        network.add("auto", "http://localhost:" + port, true);

        var card = network.getCard("auto");
        assertThat(card).isPresent();
        assertThat(card.get().getName()).isEqualTo("AutoBot");
    }

    @Test
    void addWithAutoDiscoverFalseDoesNotFetch() {
        var network = new AgentNetwork();
        network.add("manual", "http://localhost:" + port, false);

        assertThat(network.getCard("manual")).isEmpty();
        assertThat(network.get("manual")).isPresent();
    }

    @Test
    void addWithAutoDiscoverFailureStillRegistersAgent() {
        // No /.well-known/agent.json endpoint configured — discovery will fail
        app.get("/.well-known/agent.json", ctx -> ctx.status(500));

        var network = new AgentNetwork();
        network.add("failing", "http://localhost:" + port, true);

        // Agent is still registered even though discovery failed
        assertThat(network.get("failing")).isPresent();
        assertThat(network.getCard("failing")).isEmpty();
    }

    // ---- getCard and discoverNamed ------------------------------------------

    @Test
    void getCardReturnsEmptyForUnknown() {
        var network = new AgentNetwork();
        assertThat(network.getCard("nonexistent")).isEmpty();
    }

    @Test
    void discoverNamedFetchesAndCaches() throws Exception {
        app.get("/.well-known/agent.json", ctx -> {
            ctx.json(Map.of(
                "name", "NamedBot",
                "description", "Named agent",
                "url", "http://localhost:" + port,
                "version", "3.0"
            ));
        });

        var network = new AgentNetwork();
        network.add("named", "http://localhost:" + port);

        // Initially no card cached
        assertThat(network.getCard("named")).isEmpty();

        var card = network.discoverNamed("named");
        assertThat(card.getName()).isEqualTo("NamedBot");

        // Now cached
        assertThat(network.getCard("named")).isPresent();
        assertThat(network.getCard("named").get().getVersion()).isEqualTo("3.0");
    }

    @Test
    void discoverNamedThrowsForUnregisteredAgent() {
        var network = new AgentNetwork();
        assertThatThrownBy(() -> network.discoverNamed("missing"))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("missing");
    }

    // ---- Backward compatibility: add(name, url) still works -----------------

    @Test
    void addWithTwoArgsStillWorks() {
        var network = new AgentNetwork();
        network.add("compat", "http://localhost:9999");

        assertThat(network.get("compat")).isPresent().contains("http://localhost:9999");
        assertThat(network.getCard("compat")).isEmpty();
    }

    // ---- parseAgentCard unit test -------------------------------------------

    @Test
    void parseAgentCardHandlesMinimalJson() {
        var network = new AgentNetwork();
        var card = network.parseAgentCard(Map.of());

        assertThat(card.getName()).isEmpty();
        assertThat(card.getDescription()).isEmpty();
        assertThat(card.getSkills()).isEmpty();
        assertThat(card.isSupportsStreaming()).isFalse();
        assertThat(card.isSupportsPush()).isFalse();
    }
}
