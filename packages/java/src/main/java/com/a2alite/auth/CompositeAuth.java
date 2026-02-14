package com.a2alite.auth;

import java.util.List;
import java.util.Map;

/**
 * Composite authentication - tries multiple providers in order.
 *
 * <pre>{@code
 * var auth = new CompositeAuth(List.of(
 *     new APIKeyAuth(Set.of("key1")),
 *     new BearerAuth(token -> verifyToken(token))
 * ));
 * }</pre>
 */
public class CompositeAuth implements AuthProvider {
    private final List<AuthProvider> providers;

    public CompositeAuth(List<AuthProvider> providers) {
        this.providers = providers;
    }

    @Override
    public AuthResult authenticate(AuthRequest request) {
        for (var provider : providers) {
            var result = provider.authenticate(request);
            if (result.authenticated()) {
                return result;
            }
        }
        return AuthResult.failure("No valid authentication provided");
    }

    @Override
    public Map<String, Object> getScheme() {
        return Map.of(
            "oneOf", providers.stream().map(AuthProvider::getScheme).toList()
        );
    }
}
