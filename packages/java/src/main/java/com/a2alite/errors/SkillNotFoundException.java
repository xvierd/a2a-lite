package com.a2alite.errors;

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Map;

public class SkillNotFoundException extends A2ALiteException {
    private final String skill;
    private final List<String> availableSkills;

    public SkillNotFoundException(String skill, Collection<String> availableSkills) {
        super(buildMessage(skill, availableSkills));
        this.skill = skill;
        this.availableSkills = new ArrayList<>(availableSkills != null ? availableSkills : List.of());
    }

    public SkillNotFoundException(String skill) {
        this(skill, List.of());
    }

    private static String buildMessage(String skill, Collection<String> available) {
        var sb = new StringBuilder("Unknown skill '").append(skill).append("'.");
        if (available != null && !available.isEmpty()) {
            sb.append("\nAvailable skills: ").append(String.join(", ", available));
        }
        return sb.toString();
    }

    public String getSkill() { return skill; }
    public List<String> getAvailableSkills() { return availableSkills; }

    @Override
    public Map<String, Object> toResponse() {
        return Map.of(
            "error", "Unknown skill '" + skill + "'",
            "type", "SkillNotFoundException",
            "available_skills", availableSkills
        );
    }
}
