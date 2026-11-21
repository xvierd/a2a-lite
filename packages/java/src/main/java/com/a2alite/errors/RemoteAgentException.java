package com.a2alite.errors;

import java.util.Map;

public class RemoteAgentException extends A2ALiteException {
    private final Map<String, Object> response;

    public RemoteAgentException(String message, Map<String, Object> response) {
        super(message);
        this.response = response != null ? response : Map.of();
    }

    public RemoteAgentException(String message) {
        this(message, Map.of());
    }

    public Map<String, Object> getResponse() { return response; }

    /** JSON-RPC error code, when returned by the peer. */
    public Integer getCode() {
        return response.get("error") instanceof Map<?, ?> error && error.get("code") instanceof Integer code
            ? code : null;
    }

    /** Optional JSON-RPC error data as received on the wire. */
    public Object getData() {
        return response.get("error") instanceof Map<?, ?> error ? error.get("data") : null;
    }

    @Override
    public Map<String, Object> toResponse() {
        return Map.of(
            "error", getMessage(),
            "type", "RemoteAgentException",
            "remote_response", response
        );
    }
}
