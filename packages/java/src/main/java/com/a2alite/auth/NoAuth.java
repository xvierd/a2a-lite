package com.a2alite.auth;

import java.util.Map;

/**
 * No authentication (default).
 */
public class NoAuth implements AuthProvider {
    @Override
    public AuthResult authenticate(AuthRequest request) {
        return AuthResult.success("anonymous");
    }

    @Override
    public Map<String, Object> getScheme() {
        return Map.of();
    }
}
