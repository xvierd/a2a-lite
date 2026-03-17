package com.example.auth.model;

public class SecretResponse {
    private final String secret;
    private final String accessedBy;
    private final String role;

    public SecretResponse(String secret, String accessedBy, String role) {
        this.secret = secret;
        this.accessedBy = accessedBy;
        this.role = role;
    }

    public String getSecret() { return secret; }
    public String getAccessedBy() { return accessedBy; }
    public String getRole() { return role; }
}
