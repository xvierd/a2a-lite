package com.a2alite.auth;

import java.net.URI;
import java.util.Map;

/** Supplies current credentials for one explicitly configured agent endpoint. */
@FunctionalInterface
public interface CredentialProvider {
    Map<String, String> headers(URI destination);
}
