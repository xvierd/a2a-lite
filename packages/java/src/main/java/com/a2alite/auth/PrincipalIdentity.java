package com.a2alite.auth;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

/** Stable SDK subject encoding. Tenant is an independent authorization boundary. */
public final class PrincipalIdentity {
    private static final String PREFIX = "a2a:v1:";
    private static final ObjectMapper JSON = new ObjectMapper();
    private PrincipalIdentity() {}

    public static String subject(AuthResult auth) {
        if (auth.userId() == null || auth.userId().isBlank()) throw new IllegalArgumentException("Subject required");
        if (auth.namespace().isEmpty() && !auth.userId().startsWith(PREFIX)) return auth.userId();
        try {
            String tuple = JSON.writeValueAsString(new String[] {
                auth.namespace().isEmpty() ? null : auth.namespace(), auth.userId()
            });
            return PREFIX + Base64.getUrlEncoder().withoutPadding().encodeToString(tuple.getBytes(StandardCharsets.UTF_8));
        } catch (java.io.IOException e) { throw new IllegalStateException(e); }
    }
}
