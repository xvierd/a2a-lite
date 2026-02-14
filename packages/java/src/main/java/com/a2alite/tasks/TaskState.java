package com.a2alite.tasks;

/**
 * A2A Protocol task states.
 */
public enum TaskState {
    SUBMITTED("submitted"),
    WORKING("working"),
    INPUT_REQUIRED("input-required"),
    COMPLETED("completed"),
    FAILED("failed"),
    CANCELED("canceled");

    private final String value;

    TaskState(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    /**
     * Parse a string into a TaskState.
     */
    public static TaskState fromString(String text) {
        for (TaskState state : TaskState.values()) {
            if (state.value.equalsIgnoreCase(text)) {
                return state;
            }
        }
        throw new IllegalArgumentException("Unknown task state: " + text);
    }

    @Override
    public String toString() {
        return value;
    }
}
