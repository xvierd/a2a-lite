package com.a2alite.errors;

import java.util.Map;

public class A2ALiteException extends RuntimeException {
    public A2ALiteException(String message) {
        super(message);
    }

    public A2ALiteException(String message, Throwable cause) {
        super(message, cause);
    }

    public Map<String, Object> toResponse() {
        return Map.of(
            "error", getMessage(),
            "type", getClass().getSimpleName()
        );
    }
}
