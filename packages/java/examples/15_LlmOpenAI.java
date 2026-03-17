import com.a2alite.Agent;
import com.a2alite.llm.LLMSkills;

/**
 * LLM-powered agent using OpenAI via the LLMSkills factory.
 *
 * Prerequisites:
 *   export OPENAI_API_KEY=sk-...
 *
 * Run: ./gradlew run -PmainClass=LlmOpenAI
 *
 * The LLMSkills.openai() factory returns a SkillHandler that calls the
 * OpenAI Chat Completions API. The first string value in the params map
 * (keyed as "message", "text", "query", "prompt", or "input") is used
 * as the user message.
 */
class LlmOpenAI {
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("OpenAIAgent")
            .description("Agent with OpenAI-backed skills")
            .build();

        // 1. Chat — default config (gpt-4o-mini, temp 0.7, no token cap)
        agent.skill("chat", LLMSkills.openai("gpt-4o-mini"));

        // 2. Summarize — low temperature for deterministic output, capped tokens
        agent.skill("summarize", LLMSkills.openai(
            "gpt-4o-mini",
            "You are a summarizer. Condense the user's text into a brief summary.",
            0.3,
            512
        ));

        // 3. Translate — custom system prompt for translation
        agent.skill("translate", LLMSkills.openai(
            "gpt-4o-mini",
            "You are a translator. Translate the user's text into Spanish. "
                + "Reply only with the translation, nothing else.",
            0.2,
            1024
        ));

        agent.run();
    }
}
