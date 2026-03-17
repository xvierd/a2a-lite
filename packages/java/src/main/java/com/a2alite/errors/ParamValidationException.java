package com.a2alite.errors;

import java.util.List;
import java.util.Map;

public class ParamValidationException extends A2ALiteException {
    private final String skill;
    private final List<Map<String, Object>> errors;

    public ParamValidationException(String skill, List<Map<String, Object>> errors) {
        super(buildMessage(skill, errors));
        this.skill = skill;
        this.errors = errors != null ? errors : List.of();
    }

    private static String buildMessage(String skill, List<Map<String, Object>> errors) {
        var sb = new StringBuilder("Skill '").append(skill).append("' parameter error:");
        if (errors != null) {
            for (var err : errors) {
                sb.append("\n  - '")
                  .append(err.getOrDefault("field", "unknown"))
                  .append("': ")
                  .append(err.getOrDefault("message", "validation failed"));
            }
        }
        return sb.toString();
    }

    public String getSkill() { return skill; }
    public List<Map<String, Object>> getErrors() { return errors; }

    @Override
    public Map<String, Object> toResponse() {
        return Map.of(
            "error", "Skill '" + skill + "' parameter validation failed",
            "type", "ParamValidationException",
            "skill", skill,
            "validation_errors", errors
        );
    }
}
