package com.a2alite;

import com.a2alite.auth.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.Base64;
import java.util.Map;
import java.util.Set;

import static org.assertj.core.api.Assertions.assertThat;

class OAuth2AuthTest {

    private final ObjectMapper mapper = new ObjectMapper();

    /**
     * Create a simple JWT token (unsigned - for testing basic parsing).
     */
    private String createTestJwt(Map<String, Object> payload) throws Exception {
        var encoder = Base64.getUrlEncoder().withoutPadding();
        var header = encoder.encodeToString(
            mapper.writeValueAsBytes(Map.of("alg", "none", "typ", "JWT"))
        );
        var body = encoder.encodeToString(mapper.writeValueAsBytes(payload));
        return header + "." + body + ".signature";
    }

    // === OAuth2Auth Tests ===

    @Test
    void shouldRejectMissingToken() {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var result = auth.authenticate(new AuthRequest(Map.of()));
        assertThat(result.authenticated()).isFalse();
        assertThat(result.error()).contains("Bearer token required");
    }

    @Test
    void shouldRejectNonBearerAuth() {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var result = auth.authenticate(new AuthRequest(Map.of("Authorization", "Basic abc")));
        assertThat(result.authenticated()).isFalse();
        assertThat(result.error()).contains("Bearer token required");
    }

    @Test
    void shouldRejectInvalidJwtFormat() {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var result = auth.authenticate(new AuthRequest(Map.of("Authorization", "Bearer not-a-jwt")));
        assertThat(result.authenticated()).isFalse();
    }

    @Test
    void shouldValidateIssuer() throws Exception {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var token = createTestJwt(Map.of(
            "iss", "https://wrong-issuer.com",
            "sub", "user1",
            "aud", "my-agent",
            "exp", System.currentTimeMillis() / 1000 + 3600
        ));

        var result = auth.authenticate(new AuthRequest(Map.of("Authorization", "Bearer " + token)));
        assertThat(result.authenticated()).isFalse();
        assertThat(result.error()).contains("Invalid issuer");
    }

    @Test
    void shouldValidateAudience() throws Exception {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var token = createTestJwt(Map.of(
            "iss", "https://auth.example.com",
            "sub", "user1",
            "aud", "wrong-audience",
            "exp", System.currentTimeMillis() / 1000 + 3600
        ));

        var result = auth.authenticate(new AuthRequest(Map.of("Authorization", "Bearer " + token)));
        assertThat(result.authenticated()).isFalse();
        assertThat(result.error()).contains("Invalid audience");
    }

    @Test
    void shouldAcceptValidToken() throws Exception {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var token = createTestJwt(Map.of(
            "iss", "https://auth.example.com",
            "sub", "user-123",
            "aud", "my-agent",
            "exp", System.currentTimeMillis() / 1000 + 3600
        ));

        var result = auth.authenticate(new AuthRequest(Map.of("Authorization", "Bearer " + token)));
        assertThat(result.authenticated()).isTrue();
        assertThat(result.userId()).isEqualTo("user-123");
    }

    @Test
    void shouldRejectExpiredToken() throws Exception {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var token = createTestJwt(Map.of(
            "iss", "https://auth.example.com",
            "sub", "user1",
            "aud", "my-agent",
            "exp", System.currentTimeMillis() / 1000 - 3600 // expired
        ));

        var result = auth.authenticate(new AuthRequest(Map.of("Authorization", "Bearer " + token)));
        assertThat(result.authenticated()).isFalse();
        assertThat(result.error()).contains("expired");
    }

    @Test
    void shouldExtractScopes() throws Exception {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var token = createTestJwt(Map.of(
            "iss", "https://auth.example.com",
            "sub", "user1",
            "aud", "my-agent",
            "scope", "read write",
            "exp", System.currentTimeMillis() / 1000 + 3600
        ));

        var result = auth.authenticate(new AuthRequest(Map.of("Authorization", "Bearer " + token)));
        assertThat(result.authenticated()).isTrue();
        assertThat(result.scopes()).contains("read", "write");
    }

    @Test
    void shouldHandleLowercaseAuthHeader() throws Exception {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var token = createTestJwt(Map.of(
            "iss", "https://auth.example.com",
            "sub", "user1",
            "aud", "my-agent",
            "exp", System.currentTimeMillis() / 1000 + 3600
        ));

        var result = auth.authenticate(new AuthRequest(Map.of("authorization", "Bearer " + token)));
        assertThat(result.authenticated()).isTrue();
    }

    @Test
    void shouldReturnOAuth2Scheme() {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var scheme = auth.getScheme();
        assertThat(scheme.get("type")).isEqualTo("oauth2");
        assertThat(scheme).containsKey("flows");
    }

    @Test
    void shouldUseDefaultJwksUri() {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        assertThat(auth.getJwksUri()).isEqualTo("https://auth.example.com/.well-known/jwks.json");
    }

    @Test
    void shouldUseCustomJwksUri() {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent",
            "https://custom.example.com/jwks", null);
        assertThat(auth.getJwksUri()).isEqualTo("https://custom.example.com/jwks");
    }

    @Test
    void shouldHandleArrayAudience() throws Exception {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        // Create JWT with array audience manually
        var encoder = Base64.getUrlEncoder().withoutPadding();
        var header = encoder.encodeToString(
            mapper.writeValueAsBytes(Map.of("alg", "none", "typ", "JWT"))
        );
        var payload = Map.of(
            "iss", "https://auth.example.com",
            "sub", "user1",
            "aud", java.util.List.of("other-app", "my-agent"),
            "exp", System.currentTimeMillis() / 1000 + 3600
        );
        var body = encoder.encodeToString(mapper.writeValueAsBytes(payload));
        var token = header + "." + body + ".signature";

        var result = auth.authenticate(new AuthRequest(Map.of("Authorization", "Bearer " + token)));
        assertThat(result.authenticated()).isTrue();
    }

    @Test
    void shouldHandleMissingSubject() throws Exception {
        var auth = new OAuth2Auth("https://auth.example.com", "my-agent");
        var token = createTestJwt(Map.of(
            "iss", "https://auth.example.com",
            "aud", "my-agent",
            "exp", System.currentTimeMillis() / 1000 + 3600
        ));

        var result = auth.authenticate(new AuthRequest(Map.of("Authorization", "Bearer " + token)));
        assertThat(result.authenticated()).isTrue();
        assertThat(result.userId()).isEqualTo("unknown");
    }

    // === CompositeAuth Tests ===

    @Test
    void shouldTryMultipleProviders() {
        var apiKey = new APIKeyAuth(Set.of("secret-key"));
        var bearer = new BearerAuth(token -> "valid".equals(token) ? "user1" : null);
        var composite = new CompositeAuth(java.util.List.of(apiKey, bearer));

        // Should work with API key
        var result1 = composite.authenticate(new AuthRequest(Map.of("X-API-Key", "secret-key")));
        assertThat(result1.authenticated()).isTrue();

        // Should work with bearer
        var result2 = composite.authenticate(new AuthRequest(Map.of("Authorization", "Bearer valid")));
        assertThat(result2.authenticated()).isTrue();

        // Should fail with nothing valid
        var result3 = composite.authenticate(new AuthRequest(Map.of()));
        assertThat(result3.authenticated()).isFalse();
    }

    @Test
    void shouldReturnCompositeScheme() {
        var composite = new CompositeAuth(java.util.List.of(
            new APIKeyAuth(Set.of("key")),
            new BearerAuth(t -> null)
        ));
        var scheme = composite.getScheme();
        assertThat(scheme).containsKey("oneOf");
    }
}
