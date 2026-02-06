package com.a2alite;

import java.util.Map;

/**
 * Context passed to middleware functions.
 */
public record MiddlewareContext(
    String skill,
    Map<String, Object> params,
    String message,
    Map<String, Object> metadata
) {
    /**
     * Get a metadata value.
     */
    public <T> T getMetadata(String key) {
        @SuppressWarnings("unchecked")
        T value = (T) metadata.get(key);
        return value;
    }

    /**
     * Set a metadata value.
     */
    public void setMetadata(String key, Object value) {
        metadata.put(key, value);
    }
}
