package com.a2alite.persistence;

import org.a2aproject.sdk.spec.*;

import java.sql.*;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Five-second prototype worker lease, renewed while user work runs. A dead worker becomes an
 * explicit FAILED task. A later process never automatically reexecutes its user function.
 */
final class ExecutionLeases {
    static final long LEASE_MILLIS = 5000;
    private final JdbcProtocolBackend backend;

    record Claim(long fence, java.util.concurrent.atomic.AtomicBoolean entered) {}

    private final Map<String, Claim> fences = new ConcurrentHashMap<>();
    private volatile boolean closed;

    ExecutionLeases(JdbcProtocolBackend backend) {
        this.backend = backend;
    }

    void claim(String id) {
        Claim reserved = fences.get(id);
        if (reserved != null && reserved.entered().compareAndSet(false, true)) return;
        acquire(id, true);
    }

    void prepare(String id) {
        acquire(id, false);
    }

    private void acquire(String id, boolean entered) {
        if (closed) throw new IllegalStateException("Execution backend is closed");
        long fence =
                backend.transaction(
                        c -> {
                            JdbcProtocolBackend.lockOwner(c, id);
                            long now = DurableOutbox.now(c);
                            try (var s =
                                    c.prepareStatement(
                                            "UPDATE a2a_lite_owners SET"
                                                + " execution_fence=execution_fence+1,execution_until=?"
                                                + " WHERE task_id=? AND execution_until<=?"
                                                + " RETURNING execution_fence")) {
                                s.setLong(1, now + LEASE_MILLIS);
                                s.setString(2, id);
                                s.setLong(3, now);
                                try (var row = s.executeQuery()) {
                                    if (!row.next())
                                        throw new IllegalStateException(
                                                "Task already has an execution lease");
                                    return row.getLong(1);
                                }
                            }
                        });
        fences.put(id, new Claim(fence, new java.util.concurrent.atomic.AtomicBoolean(entered)));
    }

    boolean renew(String id) {
        Claim claim = fences.get(id);
        if (claim == null || closed) return false;
        long fence = claim.fence();
        return backend.transaction(
                c -> {
                    long now = DurableOutbox.now(c);
                    try (var s =
                            c.prepareStatement(
                                    "UPDATE a2a_lite_owners SET execution_until=? WHERE task_id=?"
                                            + " AND execution_fence=? AND execution_until>?")) {
                        s.setLong(1, now + LEASE_MILLIS);
                        s.setString(2, id);
                        s.setLong(3, fence);
                        s.setLong(4, now);
                        return s.executeUpdate() == 1;
                    }
                });
    }

    void validateWriter(Connection c, Task task, boolean reconciliation) throws SQLException {
        if (closed) throw new IllegalStateException("Execution backend is closed");
        if (reconciliation) return;
        try (var s =
                c.prepareStatement(
                        "SELECT execution_fence,execution_until FROM a2a_lite_owners WHERE"
                                + " task_id=?")) {
            s.setString(1, task.id());
            try (var row = s.executeQuery()) {
                if (!row.next()) throw new TaskNotFoundError();
                long current = row.getLong(1), until = row.getLong(2), now = DurableOutbox.now(c);
                Claim claim = fences.get(task.id());
                Long writer = claim == null ? null : claim.fence();
                if (writer == null) {
                    if (current > 0)
                        throw new IllegalStateException(
                                "Stale task writer without an execution lease");
                } else if (writer != current
                        || (until <= now && !task.status().state().isInterrupted()))
                    throw new IllegalStateException("Stale or expired task writer");
            }
        }
    }

    void afterSave(Connection c, Task task, boolean reconciliation) throws SQLException {
        Claim claim = fences.get(task.id());
        if (task.status().state().isInterrupted() && claim != null && !claim.entered().get())
            return;
        if (task.status().state().isFinal() || task.status().state().isInterrupted()) {
            boolean fence =
                    reconciliation || task.status().state() == TaskState.TASK_STATE_CANCELED;
            try (var s =
                    c.prepareStatement(
                            "UPDATE a2a_lite_owners SET"
                                    + " execution_until=0,execution_fence=execution_fence+? WHERE"
                                    + " task_id=?")) {
                s.setInt(1, fence ? 1 : 0);
                s.setString(2, task.id());
                s.executeUpdate();
            }
        }
    }

    Claim snapshot(String id) {
        return fences.get(id);
    }

    void committed(Task task, Claim claim) {
        if (task.status().state().isFinal()
                || (task.status().state().isInterrupted()
                        && (claim == null || claim.entered().get()))) {
            if (claim != null) fences.remove(task.id(), claim);
        }
    }

    void messageDelivered(String id) {
        Claim claim = fences.get(id);
        if (claim == null) return;
        backend.transaction(
                c -> {
                    try (var s =
                            c.prepareStatement(
                                    "DELETE FROM a2a_lite_owners o WHERE task_id=? AND"
                                        + " execution_fence=? AND NOT EXISTS (SELECT 1 FROM"
                                        + " a2a_lite_tasks t WHERE t.task_id=o.task_id)")) {
                        s.setString(1, id);
                        s.setLong(2, claim.fence());
                        if (s.executeUpdate() == 1) fences.remove(id, claim);
                    }
                    return null;
                });
    }

    int retainedClaims() {
        return fences.size();
    }

    void close() {
        closed = true;
        fences.clear();
    }

    private void clearExpiredLocalClaims() {
        fences.forEach(
                (id, claim) ->
                        backend.transaction(
                                c -> {
                                    long now = DurableOutbox.now(c);
                                    try (var s =
                                            c.prepareStatement(
                                                    "SELECT execution_fence,execution_until FROM"
                                                            + " a2a_lite_owners WHERE task_id=? FOR"
                                                            + " UPDATE")) {
                                        s.setString(1, id);
                                        try (var rows = s.executeQuery()) {
                                            if (!rows.next()
                                                    || rows.getLong(1) != claim.fence()
                                                    || rows.getLong(2) <= now) {
                                                fences.remove(id, claim);
                                                // A Message-only response never creates a Task.
                                                // Delete its expired reservation.
                                                try (var delete =
                                                        c.prepareStatement(
                                                                "DELETE FROM a2a_lite_owners o"
                                                                    + " WHERE task_id=? AND"
                                                                    + " execution_until<=? AND NOT"
                                                                    + " EXISTS (SELECT 1 FROM"
                                                                    + " a2a_lite_tasks t WHERE"
                                                                    + " t.task_id=o.task_id)")) {
                                                    delete.setString(1, id);
                                                    delete.setLong(2, now);
                                                    delete.executeUpdate();
                                                }
                                            }
                                        }
                                    }
                                    return null;
                                }));
    }

    int reconcileExpired() {
        clearExpiredLocalClaims();
        return backend.transaction(
                c -> {
                    long now = DurableOutbox.now(c);
                    // Reclaim Message-only reservations even when their original process died.
                    try (var s =
                            c.prepareStatement(
                                    "DELETE FROM a2a_lite_owners WHERE task_id IN (SELECT o.task_id"
                                        + " FROM a2a_lite_owners o WHERE execution_until<=? AND"
                                        + " created_at<=? AND NOT EXISTS (SELECT 1 FROM"
                                        + " a2a_lite_tasks t WHERE t.task_id=o.task_id) LIMIT 128"
                                        + " FOR UPDATE SKIP LOCKED)")) {
                        s.setLong(1, now);
                        s.setLong(2, now - LEASE_MILLIS);
                        s.executeUpdate();
                    }
                    var tasks = new ArrayList<Task>();
                    try (var s =
                            c.prepareStatement(
                                    "SELECT t.payload FROM a2a_lite_owners o JOIN a2a_lite_tasks t"
                                        + " ON o.task_id=t.task_id WHERE o.execution_until>0 AND"
                                        + " o.execution_until<=? AND NOT t.finalized AND t.state"
                                        + " NOT IN"
                                        + " ('TASK_STATE_INPUT_REQUIRED','TASK_STATE_AUTH_REQUIRED')"
                                        + " LIMIT 32 FOR UPDATE OF o SKIP LOCKED")) {
                        s.setLong(1, now);
                        try (var rows = s.executeQuery()) {
                            while (rows.next())
                                tasks.add(
                                        JdbcProtocolBackend.decode(rows.getString(1), Task.class));
                        }
                    }
                    for (Task task : tasks) {
                        var message =
                                Message.builder()
                                        .role(Message.Role.ROLE_AGENT)
                                        .messageId(UUID.randomUUID().toString())
                                        .parts(
                                                List.of(
                                                        new TextPart(
                                                                "Execution worker was interrupted;"
                                                                    + " the task was not"
                                                                    + " automatically retried.")))
                                        .build();
                        var failed =
                                Task.builder(task)
                                        .status(
                                                new TaskStatus(
                                                        TaskState.TASK_STATE_FAILED, message, null))
                                        .build();
                        backend.persistTask(c, failed, false, true);
                    }
                    return tasks.size();
                });
    }
}
