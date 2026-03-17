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
    boolean needsTaskContext
) {
    /**
     * Backwards-compatible constructor without needsTaskContext.
     */
    public SkillDefinition(String name, String description, List<String> tags, SkillHandler handler, boolean isStreaming) {
        this(name, description, tags, handler, isStreaming, false);
    }
}
