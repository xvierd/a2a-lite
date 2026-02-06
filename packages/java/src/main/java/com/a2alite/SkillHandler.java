package com.a2alite;

import java.util.Map;

/**
 * Functional interface for skill handlers.
 *
 * <pre>{@code
 * agent.skill("greet", params -> "Hello, " + params.get("name") + "!");
 * }</pre>
 */
@FunctionalInterface
public interface SkillHandler {
    /**
     * Handle a skill invocation.
     *
     * @param params The parameters passed to the skill
     * @return The result (will be serialized to JSON)
     * @throws Exception if an error occurs
     */
    Object handle(Map<String, Object> params) throws Exception;
}
