package com.a2alite.runtime;

import java.util.Objects;

/** Explicit deployment intent; durable requires a backend with durable state and authorization. */
public record RuntimeOptions(Profile profile, RuntimeLimits limits) {
    public enum Profile {
        LEARNING,
        AUTHENTICATED,
        DURABLE
    }

    public RuntimeOptions {
        Objects.requireNonNull(profile);
        Objects.requireNonNull(limits);
    }

    public static RuntimeOptions learning() {
        return new RuntimeOptions(Profile.LEARNING, RuntimeLimits.defaults());
    }

    public static RuntimeOptions authenticated() {
        return new RuntimeOptions(Profile.AUTHENTICATED, RuntimeLimits.defaults());
    }

    public static RuntimeOptions durable() {
        return new RuntimeOptions(Profile.DURABLE, RuntimeLimits.defaults());
    }
}
