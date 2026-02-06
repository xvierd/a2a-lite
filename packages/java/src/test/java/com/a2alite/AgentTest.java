package com.a2alite;

import com.a2alite.testing.AgentTestClient;
import org.junit.jupiter.api.Test;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

class AgentTest {

    @Test
    void shouldCreateAgentWithNameAndDescription() {
        var agent = Agent.builder()
            .name("TestBot")
            .description("A test bot")
            .build();

        assertThat(agent.getName()).isEqualTo("TestBot");
        assertThat(agent.getDescription()).isEqualTo("A test bot");
    }

    @Test
    void shouldRegisterSkill() {
        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .build();

        agent.skill("greet", params -> "Hello!");

        assertThat(agent.getSkills()).containsKey("greet");
    }

    @Test
    void shouldBuildAgentCard() {
        var agent = Agent.builder()
            .name("TestBot")
            .description("A test bot")
            .version("2.0.0")
            .build();

        agent.skill("greet", params -> "Hello");
        agent.skill("farewell", params -> "Goodbye");

        var card = agent.buildAgentCardJson("localhost", 9000);

        assertThat(card.get("name").asText()).isEqualTo("TestBot");
        assertThat(card.get("version").asText()).isEqualTo("2.0.0");
        assertThat(card.get("skills").size()).isEqualTo(2);
    }

    @Test
    void shouldCallSkillViaTestClient() throws Exception {
        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .build();

        agent.skill("greet", params -> "Hello, " + params.get("name") + "!");

        var client = new AgentTestClient(agent);
        var result = client.call("greet", Map.of("name", "World"));

        assertThat(result.getData()).isEqualTo("Hello, World!");
    }

    @Test
    void shouldReturnMapResults() throws Exception {
        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .build();

        agent.skill("info", params -> Map.of(
            "id", params.get("id"),
            "status", "active"
        ));

        var client = new AgentTestClient(agent);
        var result = client.call("info", Map.of("id", 42));
        var data = (Map<?, ?>) result.getData();

        assertThat(data.get("id")).isEqualTo(42);
        assertThat(data.get("status")).isEqualTo("active");
    }

    @Test
    void shouldListSkills() {
        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .build();

        agent.skill("skill1", params -> "one");
        agent.skill("skill2", params -> "two");

        var client = new AgentTestClient(agent);
        var skills = client.listSkills();

        assertThat(skills).contains("skill1", "skill2");
    }

    @Test
    void shouldExecuteMiddleware() throws Exception {
        var agent = Agent.builder()
            .name("Bot")
            .description("Test")
            .build();

        agent.skill("add", params ->
            (Integer) params.get("a") + (Integer) params.get("b")
        );

        // Add middleware that logs
        final StringBuilder log = new StringBuilder();
        agent.use((ctx, next) -> {
            log.append("before:");
            Object result = next.call();
            log.append("after");
            return result;
        });

        var client = new AgentTestClient(agent);
        var result = client.call("add", Map.of("a", 2, "b", 3));

        assertThat(result.getData()).isEqualTo(5);
        assertThat(log.toString()).isEqualTo("before:after");
    }
}
