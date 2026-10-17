package com.a2alite.auth;

import java.util.Set;

/**
 * Authentication result.
 */
public record AuthResult(
    boolean authenticated,
    String userId,
    Set<String> scopes,
    String error,
    boolean anonymous,
    String namespace,
    Set<String> authorizedTenants
) {
    public AuthResult {
        scopes = scopes == null ? Set.of() : Set.copyOf(scopes);
        namespace = namespace == null ? "" : namespace;
        authorizedTenants = authorizedTenants == null ? Set.of("") : Set.copyOf(authorizedTenants);
    }

    public AuthResult(boolean authenticated, String userId, Set<String> scopes, String error, boolean anonymous) {
        this(authenticated, userId, scopes, error, anonymous, "", Set.of(""));
    }

    /** Stable authenticated subject, issuer/namespace and explicitly authorized tenant membership. */
    public static AuthResult identified(String namespace, String userId, Set<String> tenants, Set<String> scopes) {
        return new AuthResult(true, userId, scopes, null, false, namespace, tenants);
    }

    /** Backwards-compatible constructor for identified authentication results. */
    public AuthResult(boolean authenticated, String userId, Set<String> scopes, String error) {
        this(authenticated, userId, scopes, error, false);
    }

    /** Explicit anonymous access, preserved through composite providers. */
    public static AuthResult anonymousAccess() {
        return new AuthResult(true, "anonymous", Set.of(), null, true);
    }

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
