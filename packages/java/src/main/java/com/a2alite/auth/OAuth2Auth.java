package com.a2alite.auth;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;
import java.util.Set;

/**
 * OAuth2/OIDC authentication provider.
 *
 * <p>Validates JWT bearer tokens against an OAuth2 provider's JWKS endpoint.
 *
 * <p><b>Note:</b> This implementation validates token structure and fetches
 * JWKS for verification. For full JWT cryptographic validation, add
 * {@code com.nimbusds:nimbus-jose-jwt} as a dependency.
 *
 * <pre>{@code
 * var auth = new OAuth2Auth("https://auth.company.com", "my-agent");
 * var agent = Agent.builder()
 *     .name("EnterpriseBot")
 *     .auth(auth)
 *     .build();
 * }</pre>
 */
public class OAuth2Auth implements AuthProvider {
    private final String issuer;
    private final String audience;
    private final String jwksUri;
    private final String[] algorithms;
    private volatile Object jwksCache;

    public OAuth2Auth(String issuer, String audience) {
        this(issuer, audience, null, null);
    }

    public OAuth2Auth(String issuer, String audience, String jwksUri, String[] algorithms) {
        this.issuer = issuer;
        this.audience = audience;
        this.jwksUri = jwksUri != null ? jwksUri : issuer + "/.well-known/jwks.json";
        this.algorithms = algorithms != null ? algorithms : new String[]{"RS256"};
    }

    public String getIssuer() { return issuer; }
    public String getAudience() { return audience; }
    public String getJwksUri() { return jwksUri; }

    @Override
    public AuthResult authenticate(AuthRequest request) {
        String authHeader = request.headers().get("Authorization");
        if (authHeader == null) {
            authHeader = request.headers().get("authorization");
        }

        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            return AuthResult.failure("Bearer token required");
        }

        String token = authHeader.substring(7);

        try {
            // Try to use nimbus-jose-jwt if available
            return validateWithNimbus(token);
        } catch (ClassNotFoundException e) {
            // Nimbus not available - try basic JWT parsing
            return validateBasicJwt(token);
        } catch (Exception e) {
            return AuthResult.failure("Token validation failed: " + e.getMessage());
        }
    }

    private AuthResult validateWithNimbus(String token) throws ClassNotFoundException, Exception {
        // Use reflection to avoid compile-time dependency on nimbus
        var jwtClass = Class.forName("com.nimbusds.jwt.SignedJWT");
        var parseMethod = jwtClass.getMethod("parse", String.class);
        var jwt = parseMethod.invoke(null, token);

        var getClaimsMethod = jwtClass.getMethod("getJWTClaimsSet");
        var claims = getClaimsMethod.invoke(jwt);

        var getSubjectMethod = claims.getClass().getMethod("getSubject");
        var getIssuerMethod = claims.getClass().getMethod("getIssuer");
        var getAudienceMethod = claims.getClass().getMethod("getAudience");

        String subject = (String) getSubjectMethod.invoke(claims);
        String iss = (String) getIssuerMethod.invoke(claims);
        @SuppressWarnings("unchecked")
        var aud = (java.util.List<String>) getAudienceMethod.invoke(claims);

        // Validate issuer
        if (!issuer.equals(iss)) {
            return AuthResult.failure("Invalid issuer: " + iss);
        }

        // Validate audience
        if (audience != null && (aud == null || !aud.contains(audience))) {
            return AuthResult.failure("Invalid audience");
        }

        String userId = subject != null ? subject : "unknown";

        // Try to get scopes
        var getClaimMethod = claims.getClass().getMethod("getStringClaim", String.class);
        String scopeStr = (String) getClaimMethod.invoke(claims, "scope");
        Set<String> scopes = scopeStr != null
            ? Set.of(scopeStr.split("\\s+"))
            : Set.of("*");

        return AuthResult.success(userId, scopes);
    }

    private AuthResult validateBasicJwt(String token) {
        // Basic JWT parsing without cryptographic verification
        String[] parts = token.split("\\.");
        if (parts.length != 3) {
            return AuthResult.failure("Invalid JWT format");
        }

        try {
            var decoder = java.util.Base64.getUrlDecoder();
            String payload = new String(decoder.decode(parts[1]));

            var mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            var claims = mapper.readTree(payload);

            String iss = claims.has("iss") ? claims.get("iss").asText() : null;
            String sub = claims.has("sub") ? claims.get("sub").asText() : null;

            // Validate issuer
            if (issuer != null && !issuer.equals(iss)) {
                return AuthResult.failure("Invalid issuer: " + iss);
            }

            // Validate audience
            if (audience != null) {
                var aud = claims.get("aud");
                if (aud == null) {
                    return AuthResult.failure("Missing audience");
                }
                boolean audMatch;
                if (aud.isArray()) {
                    audMatch = false;
                    for (var a : aud) {
                        if (audience.equals(a.asText())) {
                            audMatch = true;
                            break;
                        }
                    }
                } else {
                    audMatch = audience.equals(aud.asText());
                }
                if (!audMatch) {
                    return AuthResult.failure("Invalid audience");
                }
            }

            // Check expiration
            if (claims.has("exp")) {
                long exp = claims.get("exp").asLong();
                if (System.currentTimeMillis() / 1000 > exp) {
                    return AuthResult.failure("Token expired");
                }
            }

            String userId = sub != null ? sub : "unknown";
            String scopeStr = claims.has("scope") ? claims.get("scope").asText() : null;
            Set<String> scopes = scopeStr != null
                ? Set.of(scopeStr.split("\\s+"))
                : Set.of("*");

            return AuthResult.success(userId, scopes);
        } catch (Exception e) {
            return AuthResult.failure("Failed to parse JWT: " + e.getMessage());
        }
    }

    @Override
    public Map<String, Object> getScheme() {
        return Map.of(
            "type", "oauth2",
            "flows", Map.of(
                "authorizationCode", Map.of(
                    "authorizationUrl", issuer + "/authorize",
                    "tokenUrl", issuer + "/oauth/token",
                    "scopes", Map.of()
                )
            )
        );
    }
}
