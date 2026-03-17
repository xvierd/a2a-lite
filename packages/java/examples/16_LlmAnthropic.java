import com.a2alite.Agent;
import com.a2alite.llm.LLMSkills;

/**
 * LLM-powered agent using Anthropic (Claude) via the LLMSkills factory.
 *
 * Prerequisites:
 *   export ANTHROPIC_API_KEY=sk-ant-...
 *
 * Run: ./gradlew run -PmainClass=LlmAnthropic
 *
 * The LLMSkills.anthropic() factory returns a SkillHandler that calls the
 * Anthropic Messages API. The first string value in the params map
 * (keyed as "message", "text", "query", "prompt", or "input") is used
 * as the user message.
 */
class LlmAnthropic {
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("AnthropicAgent")
            .description("Agent with Anthropic Claude-backed skills")
            .build();

        // 1. Analyze — default config (claude-opus-4-6, temp 0.7, 1024 tokens)
        agent.skill("analyze", LLMSkills.anthropic("claude-opus-4-6"));

        // 2. Code review — low temperature, large token budget for thorough reviews
        agent.skill("code_review", LLMSkills.anthropic(
            "claude-opus-4-6",
            "You are a code reviewer. Analyze the provided code for bugs, "
                + "style issues, and potential improvements. Be concise and actionable.",
            0.3,
            2048
        ));

        // 3. Chat — general-purpose conversation
        agent.skill("chat", LLMSkills.anthropic(
            "claude-opus-4-6",
            "You are a helpful, friendly assistant.",
            0.7,
            1024
        ));

        agent.run();
    }
}
