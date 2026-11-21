package com.a2alite;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/** Skill selection shared by the SDK executor and the in-process message handler. */
record SkillCall(String name, Map<String, Object> params) {
    static SkillCall parse(String text, Set<String> skills, String textEntrySkill, ObjectMapper mapper) {
        JsonNode envelope = null;
        try {
            envelope = mapper.readTree(text);
        } catch (JsonProcessingException ignored) {
            // A plain-text message is also a valid A2A input.
        }
        if (envelope != null && envelope.has("skill")) {
            String name = envelope.path("skill").asText("");
            var params = envelope.get("params");
            return new SkillCall(name, params == null || params.isNull() ? new HashMap<>()
                : mapper.convertValue(params, new TypeReference<Map<String, Object>>() {}));
        }
        String name = textEntrySkill;
        if (name == null) name = skills.size() == 1 ? skills.iterator().next() : "";
        var params = new HashMap<String, Object>();
        params.put("message", text);
        return new SkillCall(name, params);
    }
}
