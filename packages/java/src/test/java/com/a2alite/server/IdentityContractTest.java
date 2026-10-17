package com.a2alite.server;

import static org.assertj.core.api.Assertions.*;

import com.a2alite.auth.*;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.AuthenticatedUser;
import org.junit.jupiter.api.Test;

import java.nio.file.Path;
import java.util.*;

class IdentityContractTest {
    @Test
    void sharedPrincipalAndTenantVectors() throws Exception {
        var contract =
                new ObjectMapper()
                        .readTree(Path.of("../../tests/contracts/identity.json").toFile());
        for (var vector : contract.path("vectors")) {
            var result =
                    AuthResult.identified(
                            vector.path("namespace").asText(""),
                            vector.path("userId").asText(),
                            Set.of(""),
                            Set.of());
            String principal = PrincipalIdentity.subject(result);
            assertThat(principal).isEqualTo(vector.path("principalKey").asText());
            var context =
                    new ServerCallContext(
                            new AuthenticatedUser(principal),
                            Map.of(TaskOwnership.TENANT_KEY, vector.path("tenant").asText()),
                            Set.of());
            assertThat(TaskOwnership.principal(context))
                    .isEqualTo(vector.path("ownerKey").asText());
        }
    }
}
