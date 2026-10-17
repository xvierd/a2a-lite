package com.a2alite.auth;

import java.util.Map;

/**
 * Incoming authentication request.
 */
public record AuthRequest(
    Map<String, String> headers,
    Map<String, String> queryParams
) {
    public AuthRequest {
        var normalized = new java.util.TreeMap<String, String>(String.CASE_INSENSITIVE_ORDER);
        headers.forEach((name, value) -> {
            if (normalized.putIfAbsent(name, value) != null) throw new IllegalArgumentException("Duplicate authentication header");
        });
        headers = java.util.Collections.unmodifiableMap(normalized);
        queryParams = Map.copyOf(queryParams);
    }

    public AuthRequest(Map<String, String> headers) {
        this(headers, Map.of());
    }
}
