package com.a2alite;

import com.a2alite.auth.*;
import com.nimbusds.jose.*;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.PlainJWT;
import com.nimbusds.jwt.SignedJWT;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.*;

import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.*;

class OAuth2AuthTest {
    private static final String ISSUER = "https://auth.example.com";
    private static RSAKey signingKey;
    private static RSAKey attackerKey;
    private HttpServer jwksServer;
    private OAuth2Auth auth;
    private final AtomicReference<String> jwks = new AtomicReference<>();
    private final AtomicInteger status = new AtomicInteger(200);
    private final AtomicInteger requests = new AtomicInteger();

    @BeforeAll
    static void generateKeys() throws Exception {
        signingKey = new RSAKeyGenerator(2048).keyID("trusted").generate();
        attackerKey = new RSAKeyGenerator(2048).keyID("trusted").generate();
    }

    @BeforeEach
    void setUp() throws Exception {
        jwks.set(new JWKSet(signingKey.toPublicJWK()).toString());
        jwksServer = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        jwksServer.createContext("/jwks", exchange -> {
            requests.incrementAndGet();
            byte[] body = jwks.get().getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(status.get(), body.length);
            try (var output = exchange.getResponseBody()) { output.write(body); }
        });
        jwksServer.start();
        auth = new OAuth2Auth(ISSUER, "my-agent", endpoint(), null);
    }

    @AfterEach
    void tearDown() {
        if (jwksServer != null) jwksServer.stop(0);
    }

    private String endpoint() { return "http://127.0.0.1:" + jwksServer.getAddress().getPort() + "/jwks"; }

    private JWTClaimsSet.Builder claims() {
        return new JWTClaimsSet.Builder().issuer(ISSUER).subject("user-123").audience("my-agent")
            .expirationTime(Date.from(Instant.now().plusSeconds(3600)));
    }

    private String sign(JWTClaimsSet claims) throws Exception {
        return sign(claims, signingKey, JWSAlgorithm.RS256, JOSEObjectType.JWT);
    }

    private String sign(JWTClaimsSet claims, RSAKey key, JWSAlgorithm algorithm, JOSEObjectType type) throws Exception {
        var jwt = new SignedJWT(new JWSHeader.Builder(algorithm).keyID(key.getKeyID()).type(type).build(), claims);
        jwt.sign(new RSASSASigner(key));
        return jwt.serialize();
    }

    private AuthResult authenticate(String token) {
        return auth.authenticate(new AuthRequest(Map.of("Authorization", "Bearer " + token)));
    }

    @Test
    void acceptsVerifiedSignatureAndCachesTrustedJwks() throws Exception {
        String token = sign(claims().build());
        assertThat(authenticate(token).authenticated()).isTrue();
        assertThat(authenticate(token).userId()).isEqualTo("user-123");
        assertThat(requests.get()).isEqualTo(1);
    }

    @Test
    void rejectsForgedSignatureEvenWithMatchingKeyIdAndClaims() throws Exception {
        String token = sign(claims().build(), attackerKey, JWSAlgorithm.RS256, JOSEObjectType.JWT);
        var result = authenticate(token);
        assertThat(result.authenticated()).isFalse();
        assertThat(result.error()).doesNotContain(token);
    }

    @Test
    void rejectsUnsignedAndMalformedTokens() {
        assertThat(authenticate(new PlainJWT(claims().build()).serialize()).authenticated()).isFalse();
        assertThat(authenticate("not-a-jwt").authenticated()).isFalse();
        assertThat(authenticate("").authenticated()).isFalse();
    }

    @Test
    void rejectsTamperedPayload() throws Exception {
        String token = sign(claims().build());
        String[] parts = token.split("\\.");
        String altered = sign(claims().subject("administrator").build()).split("\\.")[1];
        assertThat(authenticate(parts[0] + "." + altered + "." + parts[2]).authenticated()).isFalse();
    }

    @Test
    void rejectsAlgorithmsOutsideConfiguredAllowlist() throws Exception {
        String token = sign(claims().build(), signingKey, JWSAlgorithm.RS512, JOSEObjectType.JWT);
        assertThat(authenticate(token).authenticated()).isFalse();
        assertThat(requests.get()).isZero();
        var allowed = new OAuth2Auth(ISSUER, "my-agent", endpoint(), new String[]{"RS512"});
        assertThat(allowed.authenticate(new AuthRequest(Map.of("Authorization", "Bearer " + token))).authenticated()).isTrue();
    }

    @Test
    void rejectsUnsafeAlgorithmConfiguration() {
        for (String algorithm : List.of("none", "HS256", "unexpected")) {
            assertThatThrownBy(() -> new OAuth2Auth(ISSUER, "my-agent", endpoint(), new String[]{algorithm}))
                .isInstanceOf(IllegalArgumentException.class);
        }
    }

    @Test
    void rejectsWrongIssuerAndAudience() throws Exception {
        assertThat(authenticate(sign(claims().issuer("https://attacker.example").build())).authenticated()).isFalse();
        assertThat(authenticate(sign(claims().audience("different-agent").build())).authenticated()).isFalse();
        assertThat(authenticate(sign(claims().audience(List.of()).build())).authenticated()).isFalse();
    }

    @Test
    void rejectsExpiredNotYetValidAndNonExpiringTokens() throws Exception {
        assertThat(authenticate(sign(claims().expirationTime(Date.from(Instant.now().minusSeconds(3600))).build())).authenticated()).isFalse();
        assertThat(authenticate(sign(claims().notBeforeTime(Date.from(Instant.now().plusSeconds(3600))).build())).authenticated()).isFalse();
        assertThat(authenticate(sign(claims().expirationTime(null).build())).authenticated()).isFalse();
    }

    @Test
    void requiresARealSubjectForTaskOwnership() throws Exception {
        assertThat(authenticate(sign(claims().subject(null).build())).authenticated()).isFalse();
        assertThat(authenticate(sign(claims().subject(" ").build())).authenticated()).isFalse();
        var payload = new java.util.HashMap<>(claims().build().toJSONObject());
        payload.put("sub", 123);
        var invalid = new JWSObject(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID("trusted").build(), new Payload(payload));
        invalid.sign(new RSASSASigner(signingKey));
        assertThat(authenticate(invalid.serialize()).authenticated()).isFalse();
    }

    @Test
    void acceptsArrayAudienceAndAccessTokenType() throws Exception {
        String token = sign(claims().audience(List.of("other-agent", "my-agent")).build(),
            signingKey, JWSAlgorithm.RS256, new JOSEObjectType("at+jwt"));
        assertThat(authenticate(token).authenticated()).isTrue();
    }

    @Test
    void extractsOnlyGrantedScopesAndDeduplicatesThem() throws Exception {
        var result = authenticate(sign(claims().claim("scope", "read write read").build()));
        assertThat(result.scopes()).containsExactlyInAnyOrder("read", "write");
        assertThat(authenticate(sign(claims().build())).scopes()).isEmpty();
    }

    @Test
    void handlesAuthorizationHeaderAndSchemeCaseInsensitively() throws Exception {
        String token = sign(claims().build());
        var result = auth.authenticate(new AuthRequest(Map.of("authorization", "bearer " + token)));
        assertThat(result.authenticated()).isTrue();
    }

    @Test
    void rejectsMissingAndNonBearerAuthentication() {
        assertThat(auth.authenticate(new AuthRequest(Map.of())).authenticated()).isFalse();
        assertThat(auth.authenticate(new AuthRequest(Map.of("Authorization", "Basic abc"))).authenticated()).isFalse();
    }

    @Test
    void failsClosedWhenJwksCannotBeRetrieved() throws Exception {
        status.set(500);
        assertThat(authenticate(sign(claims().build())).authenticated()).isFalse();
    }

    @Test
    void failsClosedOnInvalidJwks() throws Exception {
        jwks.set("not json");
        assertThat(authenticate(sign(claims().build())).authenticated()).isFalse();
    }

    @Test
    void supportsPublishedRotationKeys() throws Exception {
        var next = new RSAKeyGenerator(2048).keyID("next").generate();
        jwks.set(new JWKSet(List.of(signingKey.toPublicJWK(), next.toPublicJWK())).toString());
        assertThat(authenticate(sign(claims().build())).authenticated()).isTrue();
        assertThat(authenticate(sign(claims().build(), next, JWSAlgorithm.RS256, JOSEObjectType.JWT)).authenticated()).isTrue();
    }

    @Test
    void exposesConfiguredMetadata() {
        var defaults = new OAuth2Auth(ISSUER, "my-agent");
        assertThat(defaults.getJwksUri()).isEqualTo(ISSUER + "/.well-known/jwks.json");
        assertThat(auth.getJwksUri()).isEqualTo(endpoint());
        assertThat(auth.getIssuer()).isEqualTo(ISSUER);
        assertThat(auth.getAudience()).isEqualTo("my-agent");
        assertThat(auth.getScheme()).containsEntry("type", "oauth2").containsKey("flows");
    }

    @Test
    void compositeAuthStillTriesEachProvider() {
        var composite = new CompositeAuth(List.of(new APIKeyAuth(Set.of("secret-key")),
            new BearerAuth(token -> "valid".equals(token) ? "user1" : null)));
        assertThat(composite.authenticate(new AuthRequest(Map.of("X-API-Key", "secret-key"))).authenticated()).isTrue();
        assertThat(composite.authenticate(new AuthRequest(Map.of("Authorization", "Bearer valid"))).authenticated()).isTrue();
        assertThat(composite.authenticate(new AuthRequest(Map.of())).authenticated()).isFalse();
        assertThat(composite.getScheme()).containsKey("oneOf");
    }
}
