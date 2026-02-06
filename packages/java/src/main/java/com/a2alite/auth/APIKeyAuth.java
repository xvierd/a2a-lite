package com.a2alite.auth;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * API Key authentication.
 *
 * <pre>{@code
 * var auth = new APIKeyAuth(Set.of("secret-key-1", "secret-key-2"));
 * var agent = Agent.builder()
 *     .name("SecureBot")
 *     .auth(auth)
 *     .build();
 * }</pre>
 */
public class APIKeyAuth implements AuthProvider {
    private final Set<String> keyHashes;
    private final String header;
    private final String queryParam;

    public APIKeyAuth(Set<String> keys) {
        this(keys, "X-API-Key", null);
    }

    public APIKeyAuth(Set<String> keys, String header) {
        this(keys, header, null);
    }

    public APIKeyAuth(Set<String> keys, String header, String queryParam) {
        // Store only hashes of keys for security
        this.keyHashes = keys.stream()
            .map(APIKeyAuth::hashKey)
            .collect(Collectors.toSet());
        this.header = header;
        this.queryParam = queryParam;
    }

    private static String hashKey(String key) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] hash = digest.digest(key.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(hash);
        } catch (NoSuchAlgorithmException e) {
            throw new RuntimeException("SHA-256 not available", e);
        }
    }

    @Override
    public AuthResult authenticate(AuthRequest request) {
        // Check header
        String key = request.headers().get(header);
        if (key == null) {
            key = request.headers().get(header.toLowerCase());
        }

        if (key != null) {
            String hash = hashKey(key);
            if (keyHashes.contains(hash)) {
                String userId = "api-key:" + hash.substring(0, 16);
                return AuthResult.success(userId);
            }
        }

        // Check query param
        if (queryParam != null && request.queryParams() != null) {
            String queryKey = request.queryParams().get(queryParam);
            if (queryKey != null) {
                String hash = hashKey(queryKey);
                if (keyHashes.contains(hash)) {
                    String userId = "api-key:" + hash.substring(0, 16);
                    return AuthResult.success(userId);
                }
            }
        }

        // No key provided
        if (key == null && (queryParam == null || request.queryParams() == null ||
                          !request.queryParams().containsKey(queryParam))) {
            return AuthResult.failure("API key required");
        }

        return AuthResult.failure("Invalid API key");
    }

    @Override
    public Map<String, Object> getScheme() {
        return Map.of(
            "type", "apiKey",
            "in", queryParam != null ? "query" : "header",
            "name", queryParam != null ? queryParam : header
        );
    }
}
