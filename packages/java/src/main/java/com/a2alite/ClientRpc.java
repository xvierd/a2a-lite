package com.a2alite;

import com.a2alite.errors.RemoteAgentException;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Map;
import java.util.UUID;

/** Encoding and correlation shared by unary responses and SSE data frames. */
final class ClientRpc {
    static final ObjectMapper JSON = new ObjectMapper().enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    private static final TypeReference<Map<String, Object>> OBJECT = new TypeReference<>() {};

    static String id() { return UUID.randomUUID().toString(); }

    static String encode(Object value) {
        try {
            return JSON.writeValueAsString(value);
        } catch (JsonProcessingException e) {
            throw new IllegalArgumentException("Cannot encode A2A request", e);
        }
    }

    static Map<String, Object> decode(String json) {
        try {
            var object = JSON.readValue(json, OBJECT);
            if (object != null) return object;
        } catch (JsonProcessingException ignored) {
            // A non-object response is also invalid.
        }
        throw new RemoteAgentException("Expected a JSON object from the remote agent");
    }

    static Object result(String json, String id, int status) {
        boolean success = status >= 200 && status < 300;
        String httpError = "Remote agent returned HTTP " + status;
        Map<String, Object> envelope;
        try {
            envelope = decode(json);
        } catch (RemoteAgentException malformed) {
            if (!success) throw new RemoteAgentException(httpError);
            throw malformed;
        }
        if (!"2.0".equals(envelope.get("jsonrpc")) || !id.equals(envelope.get("id"))
                || envelope.containsKey("result") == envelope.containsKey("error")) {
            throw new RemoteAgentException((success ? "" : httpError + ": ")
                + "Invalid JSON-RPC response version, id or result/error fields", envelope);
        }
        if (envelope.containsKey("error")) {
            if (!(envelope.get("error") instanceof Map<?, ?> error)
                    || !(error.get("code") instanceof Integer) || !(error.get("message") instanceof String message)) {
                throw new RemoteAgentException("Malformed JSON-RPC error", envelope);
            }
            throw new RemoteAgentException((success ? "" : httpError + ": ") + message, envelope);
        }
        if (!success) throw new RemoteAgentException(httpError, envelope);
        return envelope.get("result");
    }

    @SuppressWarnings("unchecked")
    static Map<String, Object> object(Object value, String description) {
        if (!(value instanceof Map<?, ?>)) {
            throw new RemoteAgentException("Expected " + description + " object from the remote agent");
        }
        return (Map<String, Object>) value;
    }

    private ClientRpc() {}
}
