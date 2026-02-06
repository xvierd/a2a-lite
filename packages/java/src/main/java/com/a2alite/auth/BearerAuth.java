package com.a2alite.auth;

import java.util.Map;
import java.util.function.Function;

/**
 * Bearer token authentication.
 *
 * <pre>{@code
 * var auth = new BearerAuth(token -> verifyJwt(token) != null ? getUserId(token) : null);
 * }</pre>
 */
public class BearerAuth implements AuthProvider {
    private final Function<String, String> validator;

    public BearerAuth(Function<String, String> validator) {
        this.validator = validator;
    }

    @Override
    public AuthResult authenticate(AuthRequest request) {
        String authHeader = request.headers().get("Authorization");
        if (authHeader == null) {
            authHeader = request.headers().get("authorization");
        }

        if (authHeader == null) {
            return AuthResult.failure("Authorization header required");
        }

        if (!authHeader.startsWith("Bearer ")) {
            return AuthResult.failure("Bearer token required");
        }

        String token = authHeader.substring(7);
        String userId = validator.apply(token);

        if (userId != null) {
            return AuthResult.success(userId);
        }

        return AuthResult.failure("Invalid token");
    }

    @Override
    public Map<String, Object> getScheme() {
        return Map.of(
            "type", "http",
            "scheme", "bearer"
        );
    }
}
