package com.a2alite.persistence;

import com.a2alite.push.PublicWebhookClient;

import org.a2aproject.sdk.jsonrpc.common.json.JsonUtil;
import org.a2aproject.sdk.spec.TaskPushNotificationConfig;

import java.sql.*;
import java.util.*;
import java.util.concurrent.*;

/**
 * Durable at-least-once delivery. Receivers deduplicate X-A2A-Delivery-Id; a crash after remote
 * success but before acknowledgment necessarily redelivers. Revision identifies snapshot order.
 * Deleting a config cancels queued deliveries; rotation uses the current encrypted config.
 */
public final class DurableOutbox implements AutoCloseable {
    public static final int MAX_ATTEMPTS = 8;
    public static final java.time.Duration MAX_DELIVERY_AGE = java.time.Duration.ofHours(24);

    @FunctionalInterface
    interface Delivery {
        void send(String url, String payload, Map<String, String> headers) throws Exception;
    }

    record Pending(
            String id,
            String task,
            String config,
            long revision,
            String payload,
            String encrypted,
            String token,
            int attempts) {}

    private final JdbcProtocolBackend backend;
    private ScheduledExecutorService worker;

    DurableOutbox(JdbcProtocolBackend backend) {
        this.backend = backend;
    }

    public synchronized void start() {
        if (worker != null) return;
        worker =
                Executors.newSingleThreadScheduledExecutor(
                        action -> {
                            var t = new Thread(action, "a2a-lite-outbox");
                            t.setDaemon(true);
                            return t;
                        });
        worker.scheduleWithFixedDelay(
                () -> {
                    try {
                        drainOnce();
                    } catch (RuntimeException ignored) {
                        /* Persisted work remains retryable; readiness checks storage. */
                    }
                },
                0,
                250,
                TimeUnit.MILLISECONDS);
    }

    public int drainOnce() {
        var client = new PublicWebhookClient();
        return drainOnce(client::post);
    }

    int drainOnce(Delivery delivery) {
        int delivered = 0;
        for (int i = 0; i < 16 && !Thread.currentThread().isInterrupted(); i++) {
            Pending pending = claim();
            if (pending == null) break;
            try {
                var config =
                        JsonUtil.fromJson(
                                backend.keyring.decrypt(
                                        pending.encrypted(), pending.task(), pending.config()),
                                TaskPushNotificationConfig.class);
                var headers = new HashMap<String, String>();
                headers.put("X-A2A-Delivery-Id", pending.id());
                headers.put("X-A2A-Event-Id", pending.task() + ":" + pending.revision());
                headers.put("X-A2A-Task-Revision", Long.toString(pending.revision()));
                if (config.token() != null) headers.put("X-A2A-Notification-Token", config.token());
                if (config.authentication() != null
                        && config.authentication().credentials() != null)
                    headers.put(
                            "Authorization",
                            config.authentication().scheme()
                                    + " "
                                    + config.authentication().credentials());
                delivery.send(config.url(), pending.payload(), headers);
                finish(pending, true);
                delivered++;
            } catch (Exception e) {
                finish(pending, false);
            }
        }
        return delivered;
    }

    Pending claim() {
        return backend.transaction(
                c -> {
                    long now = now(c);
                    // Claims themselves consume attempts, including a worker killed before ACK.
                    try (var expire =
                            c.prepareStatement(
                                    "UPDATE a2a_lite_outbox SET dead=TRUE,lease_token=NULL WHERE"
                                        + " event_id IN (SELECT event_id FROM a2a_lite_outbox WHERE"
                                        + " NOT delivered AND NOT dead AND lease_until<=? AND"
                                        + " (attempts>=? OR created_at<=?) LIMIT 128 FOR UPDATE"
                                        + " SKIP LOCKED)")) {
                        expire.setLong(1, now);
                        expire.setInt(2, MAX_ATTEMPTS);
                        expire.setLong(3, now - MAX_DELIVERY_AGE.toMillis());
                        expire.executeUpdate();
                    }
                    try (var s =
                            c.prepareStatement(
                                    "SELECT"
                                        + " o.event_id,o.task_id,o.config_id,o.revision,o.payload,p.encrypted,o.attempts"
                                        + " FROM a2a_lite_outbox o JOIN a2a_lite_push p ON"
                                        + " o.task_id=p.task_id AND o.config_id=p.config_id WHERE"
                                        + " NOT o.delivered AND NOT o.dead AND o.attempts<8 AND"
                                        + " o.created_at>? AND o.next_at<=? AND o.lease_until<=?"
                                        + " AND NOT EXISTS (SELECT 1 FROM a2a_lite_outbox earlier"
                                        + " WHERE earlier.task_id=o.task_id AND"
                                        + " earlier.config_id=o.config_id AND"
                                        + " earlier.revision<o.revision AND NOT earlier.delivered"
                                        + " AND NOT earlier.dead) ORDER BY o.revision,o.event_id"
                                        + " FOR UPDATE OF o SKIP LOCKED LIMIT 1")) {
                        s.setLong(1, now - MAX_DELIVERY_AGE.toMillis());
                        s.setLong(2, now);
                        s.setLong(3, now);
                        try (var row = s.executeQuery()) {
                            if (!row.next()) return null;
                            String token = UUID.randomUUID().toString();
                            var pending =
                                    new Pending(
                                            row.getString(1),
                                            row.getString(2),
                                            row.getString(3),
                                            row.getLong(4),
                                            row.getString(5),
                                            row.getString(6),
                                            token,
                                            row.getInt(7) + 1);
                            try (var update =
                                    c.prepareStatement(
                                            "UPDATE a2a_lite_outbox SET"
                                                + " lease_token=?,lease_until=?,attempts=attempts+1"
                                                + " WHERE event_id=?")) {
                                update.setString(1, token);
                                update.setLong(2, now + 30_000);
                                update.setString(3, pending.id());
                                update.executeUpdate();
                            }
                            return pending;
                        }
                    }
                });
    }

    boolean finish(Pending pending, boolean success) {
        return backend.transaction(
                c -> {
                    long now = now(c);
                    long ceiling = Math.min(300_000L, 1000L << Math.min(pending.attempts() - 1, 8));
                    long delay =
                            ThreadLocalRandom.current()
                                    .nextLong(Math.max(1, ceiling / 2), ceiling + 1);
                    try (var s =
                            c.prepareStatement(
                                    "UPDATE a2a_lite_outbox SET"
                                        + " delivered=?,dead=?,next_at=?,lease_until=0,lease_token=NULL"
                                        + " WHERE event_id=? AND lease_token=? AND"
                                        + " lease_until>?")) {
                        s.setBoolean(1, success);
                        s.setBoolean(2, !success && pending.attempts() >= MAX_ATTEMPTS);
                        s.setLong(3, now + delay);
                        s.setString(4, pending.id());
                        s.setString(5, pending.token());
                        s.setLong(6, now);
                        return s.executeUpdate() == 1;
                    }
                });
    }

    public Map<String, Long> metrics() {
        return backend.transaction(
                c -> {
                    try (var s = c.createStatement();
                            var rows =
                                    s.executeQuery(
                                            "SELECT COUNT(*) FILTER(WHERE NOT delivered AND NOT"
                                                    + " dead),COUNT(*) FILTER(WHERE dead),COUNT(*)"
                                                    + " FILTER(WHERE delivered) FROM"
                                                    + " a2a_lite_outbox")) {
                        rows.next();
                        return Map.of(
                                "pending",
                                rows.getLong(1),
                                "dead",
                                rows.getLong(2),
                                "delivered",
                                rows.getLong(3));
                    }
                });
    }

    /** Operator action: keep event IDs while retrying repaired dead letters. */
    public int retryDeadLetters() {
        return backend.transaction(
                c -> {
                    try (var s = c.createStatement()) {
                        return s.executeUpdate(
                                "UPDATE a2a_lite_outbox SET"
                                    + " dead=FALSE,attempts=0,next_at=0,created_at=CAST(EXTRACT(EPOCH"
                                    + " FROM clock_timestamp())*1000 AS BIGINT) WHERE dead");
                    }
                });
    }

    static long now(Connection c) throws SQLException {
        try (var s = c.createStatement();
                var row =
                        s.executeQuery(
                                "SELECT CAST(EXTRACT(EPOCH FROM clock_timestamp())*1000 AS"
                                        + " BIGINT)")) {
            row.next();
            return row.getLong(1);
        }
    }

    @Override
    public synchronized void close() {
        if (worker == null) return;
        worker.shutdownNow();
        try {
            worker.awaitTermination(11, TimeUnit.SECONDS);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }
}
