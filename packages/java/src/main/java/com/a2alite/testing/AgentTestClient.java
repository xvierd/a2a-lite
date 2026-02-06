package com.a2alite.testing;

import com.a2alite.Agent;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.util.List;
import java.util.Map;

/**
 * Simple test client for A2A Lite agents.
 *
 * <pre>{@code
 * var client = new AgentTestClient(agent);
 * var result = client.call("greet", Map.of("name", "World"));
 * assertThat(result).isEqualTo("Hello, World!");
 * }</pre>
 */
public class AgentTestClient {
    private final Agent agent;
    private final ObjectMapper mapper = new ObjectMapper();

    public AgentTestClient(Agent agent) {
        this.agent = agent;
    }

    /**
     * Call a skill and return the result.
     */
    public TestResult call(String skill, Map<String, Object> params) throws Exception {
        var message = mapper.createObjectNode();
        message.put("skill", skill);
        message.set("params", mapper.valueToTree(params));

        var messageWrapper = mapper.createObjectNode();
        var parts = messageWrapper.putArray("parts");
        var textPart = parts.addObject();
        textPart.put("kind", "text");
        textPart.put("text", mapper.writeValueAsString(message));

        Object data = agent.handleMessage(messageWrapper);
        String text = data instanceof String ? (String) data : mapper.writeValueAsString(data);
        return new TestResult(data, text);
    }

    /**
     * Call a skill with no parameters.
     */
    public TestResult call(String skill) throws Exception {
        return call(skill, Map.of());
    }

    /**
     * Get the agent card as JSON.
     */
    public ObjectNode getAgentCard() {
        return agent.buildAgentCardJson("localhost", 8787);
    }

    /**
     * List available skills.
     */
    public List<String> listSkills() {
        return agent.getSkills().keySet().stream().toList();
    }
}
