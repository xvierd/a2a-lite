package com.a2alite.testing;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * Structured result from a test client call.
 *
 * Provides multiple ways to access the result:
 * <ul>
 *   <li>{@link #getData()} — the raw result object</li>
 *   <li>{@link #getText()} — string representation</li>
 *   <li>{@link #as(Class)} — deserialize to a specific type</li>
 * </ul>
 */
public class TestResult {
    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final Object data;
    private final String text;

    public TestResult(Object data, String text) {
        this.data = data;
        this.text = text;
    }

    /**
     * Get the raw result data.
     */
    public Object getData() {
        return data;
    }

    /**
     * Get the string representation.
     */
    public String getText() {
        return text;
    }

    /**
     * Deserialize the result to a specific type.
     */
    public <T> T as(Class<T> clazz) {
        return MAPPER.convertValue(data, clazz);
    }

    @Override
    public String toString() {
        return "TestResult(" + data + ")";
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o instanceof TestResult other) {
            return java.util.Objects.equals(data, other.data);
        }
        // Allow direct comparison with the data value
        return java.util.Objects.equals(data, o);
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(data);
    }
}
