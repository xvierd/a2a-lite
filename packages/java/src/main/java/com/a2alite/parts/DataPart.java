package com.a2alite.parts;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;

/**
 * Structured JSON data part.
 *
 * <pre>{@code
 * var data = new DataPart(Map.of("count", 42, "status", "ok"));
 * }</pre>
 */
public class DataPart {
    private final Map<String, Object> data;

    public DataPart(Map<String, Object> data) {
        this.data = Objects.requireNonNull(data, "data is required");
    }

    /**
     * Create from A2A protocol format.
     */
    @SuppressWarnings("unchecked")
    public static DataPart fromA2A(Map<String, Object> raw) {
        var data = (Map<String, Object>) raw.getOrDefault("data", Map.of());
        return new DataPart(data);
    }

    public Map<String, Object> getData() {
        return data;
    }

    /**
     * Get a value by key.
     */
    @SuppressWarnings("unchecked")
    public <T> T get(String key) {
        return (T) data.get(key);
    }

    /**
     * Convert to A2A protocol format.
     */
    public Map<String, Object> toA2A() {
        var result = new LinkedHashMap<String, Object>();
        result.put("type", "data");
        result.put("kind", "data");
        result.put("data", data);
        return result;
    }
}
