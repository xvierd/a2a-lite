package com.a2alite.runtime;

import com.a2alite.server.ServerAdapter;

import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

/** An embedded runtime owns only its server; close never exits the hosting process. */
public final class AgentRuntime implements AutoCloseable {
    private final ServerAdapter adapter;
    private final Runnable afterClose;
    private final java.time.Duration shutdownGrace;
    private final AtomicBoolean cleanupRunning = new AtomicBoolean();
    private final AtomicBoolean closed = new AtomicBoolean();
    private final CountDownLatch terminated = new CountDownLatch(1);

    public AgentRuntime(ServerAdapter adapter, Runnable afterClose) {
        this(adapter, afterClose, java.time.Duration.ofSeconds(10));
    }

    public AgentRuntime(
            ServerAdapter adapter, Runnable afterClose, java.time.Duration shutdownGrace) {
        this.adapter = java.util.Objects.requireNonNull(adapter);
        this.afterClose = java.util.Objects.requireNonNull(afterClose);
        this.shutdownGrace = java.util.Objects.requireNonNull(shutdownGrace);
        if (shutdownGrace.isNegative() || shutdownGrace.isZero())
            throw new IllegalArgumentException("Positive shutdown grace required");
    }

    public int port() {
        return adapter.port();
    }

    public boolean ready() {
        return !closed.get() && adapter.ready();
    }

    public Map<String, Object> metrics() {
        var metrics = new java.util.HashMap<String, Object>(adapter.metrics());
        metrics.put("shutdownCleanupRunning", cleanupRunning.get());
        return Map.copyOf(metrics);
    }

    public void awaitTermination() throws InterruptedException {
        terminated.await();
    }

    @Override
    public void close() {
        if (!closed.compareAndSet(false, true)) return;
        var failure = new java.util.concurrent.atomic.AtomicReference<Throwable>();
        cleanupRunning.set(true);
        var cleanup =
                new Thread(
                        () -> {
                            try {
                                try {
                                    adapter.stop();
                                } finally {
                                    afterClose.run();
                                }
                            } catch (Throwable error) {
                                failure.set(error);
                            } finally {
                                cleanupRunning.set(false);
                            }
                        },
                        "a2a-lite-shutdown");
        cleanup.setDaemon(true);
        cleanup.start();
        try {
            long millis = shutdownGrace.toMillis();
            int nanos = (int) (shutdownGrace.minusMillis(millis).toNanos());
            cleanup.join(millis, nanos);
            if (cleanup.isAlive()) cleanup.interrupt();
            else if (failure.get() != null)
                throw new IllegalStateException("Runtime cleanup failed", failure.get());
        } catch (InterruptedException interrupted) {
            cleanup.interrupt();
            Thread.currentThread().interrupt();
        } finally {
            terminated.countDown();
        }
    }
}
