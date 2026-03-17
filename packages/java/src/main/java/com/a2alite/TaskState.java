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

    public static TaskState fromValue(String value) {
        for (var state : values()) {
            if (state.value.equals(value)) return state;
        }
        throw new IllegalArgumentException("Unknown task state: " + value);
    }

    @Override
    public String toString() { return value; }
}
