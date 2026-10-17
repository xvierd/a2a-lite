package com.a2alite.persistence;

import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.util.*;

import javax.crypto.Cipher;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Operator-supplied AES keyring: new writes use activeKeyId; retained keys decrypt older config.
 * Never store this keyring in the same database as callback credentials.
 */
public final class CallbackKeyring {
    private final Map<String, SecretKey> keys;
    private final String activeKeyId;
    private final SecureRandom random = new SecureRandom();

    public CallbackKeyring(String activeKeyId, Map<String, SecretKey> keys) {
        this.keys = Map.copyOf(keys);
        this.activeKeyId = Objects.requireNonNull(activeKeyId);
        if (!activeKeyId.matches("[A-Za-z0-9_-]{1,64}") || !keys.containsKey(activeKeyId))
            throw new IllegalArgumentException("Active callback key required");
        for (var entry : keys.entrySet()) {
            if (!entry.getKey().matches("[A-Za-z0-9_-]{1,64}")
                    || !"AES".equals(entry.getValue().getAlgorithm())
                    || !Set.of(16, 24, 32).contains(entry.getValue().getEncoded().length))
                throw new IllegalArgumentException("AES key required");
        }
    }

    public String encrypt(String value, String taskId, String configId) {
        byte[] nonce = new byte[12];
        random.nextBytes(nonce);
        try {
            var cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.ENCRYPT_MODE, keys.get(activeKeyId), new GCMParameterSpec(128, nonce));
            cipher.updateAAD(aad(taskId, configId));
            return activeKeyId
                    + "."
                    + Base64.getEncoder().encodeToString(nonce)
                    + "."
                    + Base64.getEncoder()
                            .encodeToString(cipher.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (Exception e) {
            throw new IllegalStateException("Callback encryption failed", e);
        }
    }

    public String decrypt(String value, String taskId, String configId) {
        try {
            String[] parts = value.split("\\.", -1);
            if (parts.length != 3 || !keys.containsKey(parts[0]))
                throw new IllegalArgumentException("Callback key unavailable");
            var cipher = Cipher.getInstance("AES/GCM/NoPadding");
            cipher.init(
                    Cipher.DECRYPT_MODE,
                    keys.get(parts[0]),
                    new GCMParameterSpec(128, Base64.getDecoder().decode(parts[1])));
            cipher.updateAAD(aad(taskId, configId));
            return new String(
                    cipher.doFinal(Base64.getDecoder().decode(parts[2])), StandardCharsets.UTF_8);
        } catch (Exception e) {
            throw new IllegalStateException("Callback decryption failed");
        }
    }

    private byte[] aad(String taskId, String configId) {
        return (taskId.length() + ":" + taskId + configId).getBytes(StandardCharsets.UTF_8);
    }
}
