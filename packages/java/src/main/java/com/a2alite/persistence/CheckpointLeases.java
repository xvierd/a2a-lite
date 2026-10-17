package com.a2alite.persistence;

import java.time.Duration;
import java.util.Objects;

/**
 * Experimental recovery primitive for explicitly checkpointed/idempotent workflows. A lease is not
 * an automatic retry of an ordinary skill. External side effects must accept the fencing token or
 * use their own idempotency key. DB fencing cannot undo remote effects.
 */
public final class CheckpointLeases {
    public record Lease(String jobId, String owner, long fence, String checkpoint) {}

    private final JdbcProtocolBackend backend;

    CheckpointLeases(JdbcProtocolBackend backend) {
        this.backend = backend;
    }

    public void create(String jobId, String initialCheckpoint) {
        if (jobId == null || jobId.isBlank()) throw new IllegalArgumentException("Job ID required");
        Objects.requireNonNull(initialCheckpoint);
        backend.transaction(
                c -> {
                    try (var s =
                            c.prepareStatement(
                                    "INSERT INTO a2a_lite_checkpoints(job_id,checkpoint) VALUES"
                                            + " (?,?)")) {
                        s.setString(1, jobId);
                        s.setString(2, initialCheckpoint);
                        s.executeUpdate();
                    }
                    return null;
                });
    }

    public Lease claim(String jobId, String owner, Duration duration) {
        if (owner == null
                || owner.isBlank()
                || duration.isNegative()
                || duration.isZero()
                || duration.compareTo(Duration.ofMinutes(5)) > 0)
            throw new IllegalArgumentException("Bounded lease and owner required");
        return backend.transaction(
                c -> {
                    long now = DurableOutbox.now(c);
                    try (var s =
                            c.prepareStatement(
                                    "UPDATE a2a_lite_checkpoints SET"
                                        + " owner=?,fence=fence+1,lease_until=? WHERE job_id=? AND"
                                        + " NOT completed AND lease_until<=? RETURNING"
                                        + " fence,checkpoint")) {
                        s.setString(1, owner);
                        s.setLong(2, Math.addExact(now, duration.toMillis()));
                        s.setString(3, jobId);
                        s.setLong(4, now);
                        try (var row = s.executeQuery()) {
                            return row.next()
                                    ? new Lease(jobId, owner, row.getLong(1), row.getString(2))
                                    : null;
                        }
                    }
                });
    }

    public void checkpoint(Lease lease, String checkpoint, Duration extendBy, boolean completed) {
        if (extendBy.isNegative()
                || extendBy.isZero()
                || extendBy.compareTo(Duration.ofMinutes(5)) > 0)
            throw new IllegalArgumentException("Bounded lease required");
        Objects.requireNonNull(checkpoint);
        backend.transaction(
                c -> {
                    long now = DurableOutbox.now(c);
                    try (var s =
                            c.prepareStatement(
                                    "UPDATE a2a_lite_checkpoints SET"
                                        + " checkpoint=?,completed=?,lease_until=? WHERE job_id=?"
                                        + " AND owner=? AND fence=? AND lease_until>? AND NOT"
                                        + " completed")) {
                        s.setString(1, checkpoint);
                        s.setBoolean(2, completed);
                        s.setLong(3, completed ? 0 : Math.addExact(now, extendBy.toMillis()));
                        s.setString(4, lease.jobId());
                        s.setString(5, lease.owner());
                        s.setLong(6, lease.fence());
                        s.setLong(7, now);
                        if (s.executeUpdate() != 1)
                            throw new IllegalStateException("Stale or expired execution lease");
                    }
                    return null;
                });
    }
}
