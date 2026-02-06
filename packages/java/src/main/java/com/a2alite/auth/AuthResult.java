package com.a2alite.auth;

import java.util.Set;

/**
 * Authentication result.
 */
public record AuthResult(
    boolean authenticated,
    String userId,
    Set<String> scopes,
    String error
) {
    /**
     * Create a successful authentication result.
     */
    public static AuthResult success(String userId) {
        return new AuthResult(true, userId, Set.of("*"), null);
    }

    /**
     * Create a successful authentication result with scopes.
     */
    public static AuthResult success(String userId, Set<String> scopes) {
        return new AuthResult(true, userId, scopes, null);
    }

    /**
     * Create a failed authentication result.
     */
    public static AuthResult failure(String error) {
        return new AuthResult(false, null, Set.of(), error);
    }
}
