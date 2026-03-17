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

    @Override
    public Map<String, Object> toResponse() {
        return Map.of(
            "error", getMessage(),
            "type", "RemoteAgentException",
            "remote_response", response
        );
    }
}
