package com.a2alite;

import java.util.List;

/**
 * Definition of a registered skill.
 */
public record SkillDefinition(
    String name,
    String description,
    List<String> tags,
    SkillHandler handler,
    boolean isStreaming,
    boolean needsTaskContext,
    boolean needsInteraction
) {
    /**
     * Create a simple skill definition.
     */
    public SkillDefinition(String name, String description, List<String> tags,
                          SkillHandler handler, boolean isStreaming) {
        this(name, description, tags, handler, isStreaming, false, false);
    }
}
