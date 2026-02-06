package com.a2alite.auth;

import java.util.Map;

/**
 * Base interface for authentication providers.
 */
public interface AuthProvider {
    /**
     * Authenticate a request.
     *
     * @param request The authentication request
     * @return The authentication result
     */
    AuthResult authenticate(AuthRequest request);

    /**
     * Get the A2A security scheme definition.
     */
    Map<String, Object> getScheme();
}
