package com.a2alite;

public enum TaskState {
    SUBMITTED("submitted"),
    WORKING("working"),
    INPUT_REQUIRED("input-required"),
    COMPLETED("completed"),
    FAILED("failed"),
    CANCELED("canceled"),
    AUTH_REQUIRED("auth-required");

    private final String value;

    TaskState(String value) {
        this.value = value;
    }

    public String getValue() { return value; }

    /**
     * Parse a TaskState from its string value (e.g. "submitted", "working").
     */
    public static TaskState fromString(String text) {
        for (var state : values()) {
            if (state.value.equalsIgnoreCase(text)) return state;
        }
        throw new IllegalArgumentException("Unknown task state: " + text);
    }

    /** @deprecated Use {@link #fromString(String)} instead. */
    @Deprecated
    public static TaskState fromValue(String value) {
        return fromString(value);
    }

    @Override
    public String toString() { return value; }
}
