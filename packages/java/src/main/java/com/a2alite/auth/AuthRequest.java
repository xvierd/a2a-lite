package com.a2alite.auth;

import java.util.Map;

/**
 * Incoming authentication request.
 */
public record AuthRequest(
    Map<String, String> headers,
    Map<String, String> queryParams
) {
    public AuthRequest(Map<String, String> headers) {
        this(headers, Map.of());
    }
}
