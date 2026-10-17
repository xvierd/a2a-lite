package com.a2alite.server;

import com.a2alite.runtime.RuntimeLimits;

import org.a2aproject.sdk.server.ServerCallContext;

import java.util.Map;
import java.util.Set;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.function.UnaryOperator;

/** Admission and execution lifetime remain separate from SSE consumer lifetime. */
final class RuntimeController implements AutoCloseable {
    private final RuntimeLimits limits;
    private final Semaphore tasks;
    private final Semaphore streams;
    private final java.util.HashMap<String, Integer> principalTasks = new java.util.HashMap<>();
    private final java.util.HashMap<String, Integer> principalStreams = new java.util.HashMap<>();
    private final AtomicBoolean draining = new AtomicBoolean();
    private final AtomicLong accepted = new AtomicLong(),
            rejected = new AtomicLong(),
            timedOut = new AtomicLong();
    private final Set<Thread> running = ConcurrentHashMap.newKeySet();
    private final ScheduledExecutorService deadlines =
            Executors.newSingleThreadScheduledExecutor(
                    r -> {
                        var thread = new Thread(r, "a2a-lite-deadlines");
                        thread.setDaemon(true);
                        return thread;
                    });

    RuntimeController(RuntimeLimits limits) {
        this.limits = limits;
        tasks = new Semaphore(limits.maxActiveTasks());
        streams = new Semaphore(limits.maxStreams());
    }

    Lease admitTask(ServerCallContext context) {
        var lease =
                acquire(tasks, principalTasks, principal(context), limits.maxTasksPerPrincipal());
        accepted.incrementAndGet();
        context.getState()
                .put(
                        ServerCallContext.EXECUTION_WRAPPER_KEY,
                        (UnaryOperator<Runnable>)
                                action -> {
                                    lease.claimed.set(true);
                                    return () -> {
                                        synchronized (lease) {
                                            if (lease.released.get()) return;
                                            lease.started = true;
                                        }
                                        Thread thread = Thread.currentThread();
                                        running.add(thread);
                                        var finished = new AtomicBoolean();
                                        Object lifecycle = new Object();
                                        java.util.concurrent.ScheduledFuture<?> deadline = null;
                                        try {
                                            deadline =
                                                    deadlines.schedule(
                                                            () -> {
                                                                synchronized (lifecycle) {
                                                                    if (!finished.get()) {
                                                                        timedOut.incrementAndGet();
                                                                        thread.interrupt();
                                                                    }
                                                                }
                                                            },
                                                            limits.executionTimeout().toNanos(),
                                                            TimeUnit.NANOSECONDS);
                                            action.run();
                                        } finally {
                                            synchronized (lifecycle) {
                                                finished.set(true);
                                                if (deadline != null) deadline.cancel(false);
                                            }
                                            running.remove(thread);
                                            lease.release();
                                            Thread.interrupted();
                                        }
                                    };
                                });
        return lease;
    }

    Lease admitStream(ServerCallContext context) {
        return acquire(
                streams, principalStreams, principal(context), limits.maxStreamsPerPrincipal());
    }

    private String principal(ServerCallContext context) {
        // Admission is identity-wide, so an identity cannot multiply its quota using tenants.
        return (context.getUser().isAuthenticated() ? "identified:" : "anonymous:")
                + context.getUser().getUsername();
    }

    private synchronized Lease acquire(
            Semaphore semaphore,
            java.util.Map<String, Integer> counts,
            String principal,
            int maximum) {
        if (counts.getOrDefault(principal, 0) >= maximum) {
            rejected.incrementAndGet();
            throw new RuntimeOverloadedException();
        }
        if (draining.get() || !semaphore.tryAcquire()) {
            rejected.incrementAndGet();
            throw new RuntimeOverloadedException();
        }
        counts.merge(principal, 1, Integer::sum);
        var lease =
                new Lease(
                        semaphore,
                        () -> {
                            synchronized (RuntimeController.this) {
                                counts.computeIfPresent(
                                        principal, (key, count) -> count == 1 ? null : count - 1);
                            }
                        });
        if (draining.get()) {
            lease.release();
            rejected.incrementAndGet();
            throw new RuntimeOverloadedException();
        }
        return lease;
    }

    boolean ready() {
        return !draining.get();
    }

    Map<String, Object> metrics() {
        return Map.of(
                "activeTasks",
                limits.maxActiveTasks() - tasks.availablePermits(),
                "activeStreams",
                limits.maxStreams() - streams.availablePermits(),
                "accepted",
                accepted.get(),
                "rejected",
                rejected.get(),
                "timedOut",
                timedOut.get(),
                "draining",
                draining.get(),
                "executionsStillRunning",
                running.size());
    }

    @Override
    public void close() {
        if (!draining.compareAndSet(false, true)) return;
        long until = System.nanoTime() + limits.shutdownGrace().toNanos();
        while (tasks.availablePermits() != limits.maxActiveTasks() && System.nanoTime() < until) {
            try {
                TimeUnit.MILLISECONDS.sleep(10);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                break;
            }
        }
        running.forEach(Thread::interrupt);
        deadlines.shutdownNow();
    }

    static final class Lease implements AutoCloseable {
        private final Semaphore semaphore;
        private final Runnable afterRelease;
        final AtomicBoolean claimed = new AtomicBoolean();
        private final AtomicBoolean released = new AtomicBoolean();
        private boolean started;

        Lease(Semaphore semaphore, Runnable afterRelease) {
            this.semaphore = semaphore;
            this.afterRelease = afterRelease;
        }

        synchronized void abort() {
            if (!started) release();
        }

        void release() {
            if (released.compareAndSet(false, true)) {
                semaphore.release();
                afterRelease.run();
            }
        }

        @Override
        public void close() {
            if (!claimed.get()) release();
        }
    }
}
