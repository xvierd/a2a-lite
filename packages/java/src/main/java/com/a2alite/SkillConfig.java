package com.a2alite;

import java.util.List;

/**
 * Configuration for a skill.
 *
 * <pre>{@code
 * agent.skill("greet", SkillConfig.of("Greet someone"), params -> ...);
 * agent.skill("chat", SkillConfig.streaming(), params -> ...);
 * }</pre>
 */
public record SkillConfig(
    String description,
    List<String> tags,
    boolean streaming
) {
    /**
     * Create a streaming skill configuration.
     */
    public static SkillConfig withStreaming() {
        return new SkillConfig(null, null, true);
    }

    /**
     * Create a skill configuration with a description.
     */
    public static SkillConfig of(String description) {
        return new SkillConfig(description, null, false);
    }

    /**
     * Create a skill configuration with description and tags.
     */
    public static SkillConfig of(String description, List<String> tags) {
        return new SkillConfig(description, tags, false);
    }

    /**
     * Create a skill configuration with description, tags, and streaming flag.
     */
    public static SkillConfig of(String description, List<String> tags, boolean streaming) {
        return new SkillConfig(description, tags, streaming);
    }
}
