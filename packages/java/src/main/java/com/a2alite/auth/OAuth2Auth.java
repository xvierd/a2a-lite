package com.a2alite.auth;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.source.JWKSourceBuilder;
import com.nimbusds.jose.proc.DefaultJOSEObjectTypeVerifier;
import com.nimbusds.jose.proc.JWSVerificationKeySelector;
import com.nimbusds.jose.proc.SecurityContext;
import com.nimbusds.jose.util.DefaultResourceRetriever;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.nimbusds.jwt.proc.DefaultJWTClaimsVerifier;
import com.nimbusds.jwt.proc.DefaultJWTProcessor;

import java.net.URI;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

/**
 * OAuth2/OIDC bearer authentication with mandatory JWKS signature verification.
 *
 * <p>Verifies issuer, audience, expiry and subject after signature verification.
 * Only configured asymmetric algorithms are accepted (RS256 by default).
 * The JWKS endpoint is configuration and is never taken from a token.
 */
public class OAuth2Auth implements AuthProvider {
    private static final Set<String> SIGNATURE_ALGORITHMS = Set.of(
        "RS256", "RS384", "RS512", "PS256", "PS384", "PS512",
        "ES256", "ES384", "ES512", "EdDSA"
    );
    private final String issuer;
    private final String audience;
    private final String jwksUri;
    private final DefaultJWTProcessor<SecurityContext> processor;

    public OAuth2Auth(String issuer, String audience) {
        this(issuer, audience, null, null);
    }

    public OAuth2Auth(String issuer, String audience, String jwksUri, String[] algorithms) {
        if (issuer == null || issuer.isBlank()) throw new IllegalArgumentException("An OAuth2 issuer is required");
        this.issuer = issuer;
        this.audience = audience;
        this.jwksUri = jwksUri != null ? jwksUri : issuer.replaceAll("/+$", "") + "/.well-known/jwks.json";
        String[] configured = algorithms != null ? algorithms : new String[]{"RS256"};
        if (configured.length == 0 || Arrays.stream(configured).anyMatch(a -> a == null || !SIGNATURE_ALGORITHMS.contains(a))) {
            throw new IllegalArgumentException("Use an explicit asymmetric JWT signature algorithm");
        }
        var allowed = Arrays.stream(configured).map(JWSAlgorithm::parse).collect(Collectors.toUnmodifiableSet());
        try {
            var endpoint = URI.create(this.jwksUri);
            if (endpoint.getHost() == null || endpoint.getUserInfo() != null || endpoint.getFragment() != null
                    || !("https".equals(endpoint.getScheme()) || "http".equals(endpoint.getScheme()))) {
                throw new IllegalArgumentException("JWKS endpoint must be an HTTP(S) URL without credentials or a fragment");
            }
            // Bounded retrieval and cached rotation, without background threads.
            var source = JWKSourceBuilder.<SecurityContext>create(
                endpoint.toURL(), new DefaultResourceRetriever(5000, 5000, 100_000)
            ).refreshAheadCache(false).retrying(false).build();
            processor = new DefaultJWTProcessor<>();
            processor.setJWSKeySelector(new JWSVerificationKeySelector<>(allowed, source));
            processor.setJWSTypeVerifier(new DefaultJOSEObjectTypeVerifier<>(
                new HashSet<>(Arrays.asList(JOSEObjectType.JWT, new JOSEObjectType("at+jwt"), null))
            ));
            var claims = new DefaultJWTClaimsVerifier<SecurityContext>(
                audience == null ? null : Set.of(audience), new JWTClaimsSet.Builder().issuer(issuer).build(),
                Set.of("iss", "sub", "exp"), null
            );
            claims.setMaxClockSkew(30);
            processor.setJWTClaimsSetVerifier(claims);
        } catch (java.net.MalformedURLException e) {
            throw new IllegalArgumentException("Invalid JWKS endpoint", e);
        }
    }

    public String getIssuer() { return issuer; }
    public String getAudience() { return audience; }
    public String getJwksUri() { return jwksUri; }

    @Override
    public AuthResult authenticate(AuthRequest request) {
        String header = request.headers().entrySet().stream()
            .filter(entry -> "Authorization".equalsIgnoreCase(entry.getKey()))
            .map(Map.Entry::getValue).findFirst().orElse(null);
        if (header == null || !header.regionMatches(true, 0, "Bearer ", 0, 7)) {
            return AuthResult.failure("Bearer token required");
        }
        String token = header.substring(7).trim();
        if (token.isEmpty() || token.length() > 65_536) return AuthResult.failure("Invalid bearer token");
        try {
            var signed = SignedJWT.parse(token);
            // Check the JSON type before any library claim coercion.
            Object rawSubject = signed.getPayload().toJSONObject().get("sub");
            if (!(rawSubject instanceof String) || ((String) rawSubject).isBlank()) {
                return AuthResult.failure("Token subject required");
            }
            JWTClaimsSet claims = processor.process(signed, null);
            String subject = claims.getSubject();
            if (subject == null || subject.isBlank()) return AuthResult.failure("Token subject required");
            String scope = claims.getStringClaim("scope");
            Set<String> scopes = scope == null || scope.isBlank() ? Set.of()
                : Arrays.stream(scope.trim().split("\\s+")).collect(Collectors.toUnmodifiableSet());
            return AuthResult.identified(issuer, subject, Set.of(""), scopes);
        } catch (Exception e) {
            // Tokens, provider responses and parsing details may contain credentials.
            return AuthResult.failure("Invalid bearer token");
        }
    }

    @Override
    public Map<String, Object> getScheme() {
        return Map.of("type", "oauth2", "flows", Map.of("authorizationCode", Map.of(
            "authorizationUrl", issuer + "/authorize", "tokenUrl", issuer + "/oauth/token", "scopes", Map.of()
        )));
    }
}
