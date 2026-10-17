package com.a2alite.runtime;

import java.time.Duration;
import java.util.Objects;

/** Finite process-local limits. Execution interruption is cooperative, not sandbox isolation. */
public record RuntimeLimits(
        int maxActiveTasks,
        int maxStreams,
        int maxRequestBytes,
        int maxResultBytes,
        int maxHistoryLength,
        int maxPushConfigsPerTask,
        int maxTasksPerPrincipal,
        int maxStreamsPerPrincipal,
        int maxStoredTasks,
        int maxEventsPerExecution,
        Duration executionTimeout,
        Duration streamTimeout,
        Duration shutdownGrace) {
    public RuntimeLimits {
        if (maxActiveTasks < 1
                || maxStreams < 1
                || maxRequestBytes < 1
                || maxResultBytes < 1
                || maxHistoryLength < 1
                || maxPushConfigsPerTask < 1
                || maxTasksPerPrincipal < 1
                || maxStreamsPerPrincipal < 1
                || maxStoredTasks < 1
                || maxEventsPerExecution < 1)
            throw new IllegalArgumentException("Limits must be positive");
        for (var duration : new Duration[] {executionTimeout, streamTimeout, shutdownGrace}) {
            Objects.requireNonNull(duration);
            if (duration.isNegative() || duration.isZero())
                throw new IllegalArgumentException("Timeouts must be positive");
        }
    }

    public RuntimeLimits(
            int tasks,
            int streams,
            int requestBytes,
            int resultBytes,
            int history,
            int pushConfigs,
            int tasksPerPrincipal,
            int streamsPerPrincipal,
            int storedTasks,
            Duration execution,
            Duration stream,
            Duration shutdown) {
        this(
                tasks,
                streams,
                requestBytes,
                resultBytes,
                history,
                pushConfigs,
                tasksPerPrincipal,
                streamsPerPrincipal,
                storedTasks,
                4096,
                execution,
                stream,
                shutdown);
    }

    /** Compatibility constructor with finite principal and storage defaults. */
    public RuntimeLimits(
            int tasks,
            int streams,
            int requestBytes,
            int resultBytes,
            int history,
            int pushConfigs,
            Duration execution,
            Duration stream,
            Duration shutdown) {
        this(
                tasks,
                streams,
                requestBytes,
                resultBytes,
                history,
                pushConfigs,
                Math.min(8, tasks),
                Math.min(16, streams),
                10_000,
                execution,
                stream,
                shutdown);
    }

    public static RuntimeLimits defaults() {
        return new RuntimeLimits(
                32,
                64,
                1_048_576,
                1_048_576,
                100,
                16,
                Duration.ofMinutes(5),
                Duration.ofMinutes(5),
                Duration.ofSeconds(10));
    }
}
