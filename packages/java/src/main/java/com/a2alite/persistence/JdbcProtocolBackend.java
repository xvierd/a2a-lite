package com.a2alite.persistence;

import com.a2alite.runtime.RuntimeLimits;
import com.a2alite.server.ProtocolBackend;
import com.a2alite.server.TaskOwnership;

import org.a2aproject.sdk.jsonrpc.common.json.JsonUtil;
import org.a2aproject.sdk.jsonrpc.common.wrappers.ListTasksResult;
import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.*;
import org.a2aproject.sdk.server.tasks.*;
import org.a2aproject.sdk.spec.*;

import java.sql.*;
import java.time.Instant;
import java.util.*;

import javax.sql.DataSource;

/**
 * PostgreSQL reference backend. State/ownership are durable; running Java functions and live SDK
 * event queues are not resumed or replicated. Each task revision and its callback outbox rows
 * commit in one transaction. Apply initializeSchema explicitly before starting a runtime.
 */
public final class JdbcProtocolBackend
        implements ProtocolBackend,
                TaskStore,
                TaskStateProvider,
                TaskAuthorizationProvider,
                PushNotificationConfigStore {
    final DataSource source;
    final CallbackKeyring keyring;
    private final RuntimeLimits limits;
    private final boolean automaticDelivery;
    private final DurableOutbox outbox;
    private final JdbcTaskCoordination coordination;
    final ExecutionLeases executions;

    public JdbcProtocolBackend(DataSource source, CallbackKeyring keyring, RuntimeLimits limits) {
        this(source, keyring, limits, true);
    }

    /**
     * Disable automatic callback dispatch during isolated restores/tests; outbox commits remain
     * atomic.
     */
    public JdbcProtocolBackend(
            DataSource source,
            CallbackKeyring keyring,
            RuntimeLimits limits,
            boolean automaticDelivery) {
        this.automaticDelivery = automaticDelivery;
        this.source = Objects.requireNonNull(source);
        this.keyring = Objects.requireNonNull(keyring);
        this.limits = Objects.requireNonNull(limits);
        this.outbox = new DurableOutbox(this);
        this.coordination = new JdbcTaskCoordination(this, limits.maxStreams());
        this.executions = new ExecutionLeases(this);
    }

    public void initializeSchema() {
        transaction(
                c -> {
                    for (String sql :
                            List.of(
                                    "CREATE TABLE IF NOT EXISTS a2a_lite_schema (version INTEGER"
                                            + " PRIMARY KEY)",
                                    "CREATE TABLE IF NOT EXISTS a2a_lite_owners (task_id TEXT"
                                        + " PRIMARY KEY, principal TEXT NOT NULL, identified"
                                        + " BOOLEAN NOT NULL, execution_fence BIGINT NOT NULL"
                                        + " DEFAULT 0, execution_until BIGINT NOT NULL DEFAULT 0)",
                                    "ALTER TABLE a2a_lite_owners ADD COLUMN IF NOT EXISTS"
                                            + " execution_fence BIGINT NOT NULL DEFAULT 0",
                                    "ALTER TABLE a2a_lite_owners ADD COLUMN IF NOT EXISTS"
                                            + " execution_until BIGINT NOT NULL DEFAULT 0",
                                    "ALTER TABLE a2a_lite_owners ADD COLUMN IF NOT EXISTS"
                                        + " created_at BIGINT NOT NULL DEFAULT (CAST(EXTRACT(EPOCH"
                                        + " FROM clock_timestamp())*1000 AS BIGINT))",
                                    "CREATE TABLE IF NOT EXISTS a2a_lite_tasks (task_id TEXT"
                                        + " PRIMARY KEY REFERENCES a2a_lite_owners(task_id) ON"
                                        + " DELETE CASCADE, payload TEXT NOT NULL, revision BIGINT"
                                        + " NOT NULL, context_id TEXT, state TEXT NOT NULL,"
                                        + " updated_at BIGINT NOT NULL, finalized BOOLEAN NOT"
                                        + " NULL)",
                                    "CREATE INDEX IF NOT EXISTS a2a_lite_owner_lookup ON"
                                            + " a2a_lite_owners (principal,identified)",
                                    "CREATE TABLE IF NOT EXISTS a2a_lite_events (task_id TEXT NOT"
                                            + " NULL REFERENCES a2a_lite_owners(task_id) ON DELETE"
                                            + " CASCADE, revision BIGINT NOT NULL, payload TEXT NOT"
                                            + " NULL, PRIMARY KEY(task_id,revision))",
                                    "CREATE INDEX IF NOT EXISTS a2a_lite_task_page ON"
                                            + " a2a_lite_tasks (updated_at DESC,task_id)",
                                    "CREATE TABLE IF NOT EXISTS a2a_lite_push (task_id TEXT NOT"
                                        + " NULL REFERENCES a2a_lite_owners(task_id) ON DELETE"
                                        + " CASCADE, config_id TEXT NOT NULL, encrypted TEXT NOT"
                                        + " NULL, protocol TEXT NOT NULL, PRIMARY"
                                        + " KEY(task_id,config_id))",
                                    "CREATE TABLE IF NOT EXISTS a2a_lite_outbox (event_id TEXT"
                                        + " PRIMARY KEY, task_id TEXT NOT NULL, config_id TEXT NOT"
                                        + " NULL, revision BIGINT NOT NULL, payload TEXT NOT NULL,"
                                        + " attempts INTEGER NOT NULL DEFAULT 0, next_at BIGINT NOT"
                                        + " NULL DEFAULT 0, lease_until BIGINT NOT NULL DEFAULT 0,"
                                        + " lease_token TEXT, delivered BOOLEAN NOT NULL DEFAULT"
                                        + " FALSE, dead BOOLEAN NOT NULL DEFAULT FALSE,"
                                        + " UNIQUE(task_id,config_id,revision), FOREIGN"
                                        + " KEY(task_id,config_id) REFERENCES"
                                        + " a2a_lite_push(task_id,config_id) ON DELETE CASCADE)",
                                    "ALTER TABLE a2a_lite_outbox ADD COLUMN IF NOT EXISTS"
                                        + " created_at BIGINT NOT NULL DEFAULT (CAST(EXTRACT(EPOCH"
                                        + " FROM clock_timestamp())*1000 AS BIGINT))",
                                    "CREATE UNIQUE INDEX IF NOT EXISTS a2a_lite_outbox_revision ON"
                                            + " a2a_lite_outbox(task_id,config_id,revision)",
                                    "CREATE INDEX IF NOT EXISTS a2a_lite_outbox_due ON"
                                        + " a2a_lite_outbox (delivered,dead,next_at,lease_until)",
                                    "CREATE TABLE IF NOT EXISTS a2a_lite_checkpoints (job_id TEXT"
                                        + " PRIMARY KEY, checkpoint TEXT NOT NULL, owner TEXT,"
                                        + " fence BIGINT NOT NULL DEFAULT 0, lease_until BIGINT NOT"
                                        + " NULL DEFAULT 0, completed BOOLEAN NOT NULL DEFAULT"
                                        + " FALSE)")) {
                        try (var statement = c.createStatement()) {
                            statement.execute(sql);
                        }
                    }
                    try (var statement = c.createStatement();
                            var rows =
                                    statement.executeQuery("SELECT version FROM a2a_lite_schema")) {
                        if (rows.next()) {
                            if (rows.getInt(1) != 1 || rows.next())
                                throw new IllegalStateException("Unsupported persistence schema");
                        } else {
                            try (var insert = c.createStatement()) {
                                insert.executeUpdate(
                                        "INSERT INTO a2a_lite_schema(version) VALUES (1)");
                            }
                        }
                    }
                    return null;
                });
    }

    @Override
    public TaskStore tasks() {
        return this;
    }

    @Override
    public TaskStateProvider taskStates() {
        return this;
    }

    @Override
    public TaskAuthorizationProvider authorization() {
        return this;
    }

    @Override
    public PushNotificationConfigStore pushConfigs() {
        return this;
    }

    @Override
    public boolean durable() {
        return true;
    }

    @Override
    public boolean durableNotifications() {
        return true;
    }

    @Override
    public void start() {
        if (!ready()) throw new IllegalStateException("Protocol database unavailable");
        if (automaticDelivery) outbox.start();
        coordination.start();
    }

    @Override
    public void close() {
        coordination.close();
        outbox.close();
        executions.close();
    }

    @Override
    public org.a2aproject.sdk.server.agentexecution.AgentExecutor executor(
            org.a2aproject.sdk.server.agentexecution.AgentExecutor delegate) {
        return coordination.executor(delegate);
    }

    @Override
    public java.util.concurrent.Flow.Publisher<StreamingEventKind> subscribe(String taskId) {
        return coordination.subscribe(taskId);
    }

    public DurableOutbox outbox() {
        return outbox;
    }

    public CheckpointLeases checkpoints() {
        return new CheckpointLeases(this);
    }

    @Override
    public boolean ready() {
        try (var c = source.getConnection();
                var s = c.createStatement();
                var rows = s.executeQuery("SELECT version FROM a2a_lite_schema")) {
            return rows.next() && rows.getInt(1) == 1 && !rows.next();
        } catch (SQLException e) {
            return false;
        }
    }

    @Override
    public boolean checkRead(ServerCallContext context, String taskId, TaskOperation operation) {
        return operation == TaskOperation.LIST_TASKS && taskId.isEmpty() || owns(context, taskId);
    }

    @Override
    public boolean checkWrite(ServerCallContext context, String taskId, TaskOperation operation) {
        return owns(context, taskId);
    }

    @Override
    public boolean checkCreate(ServerCallContext context, TaskOperation operation) {
        return context.getUser().isAuthenticated();
    }

    private boolean owns(ServerCallContext context, String id) {
        return transaction(
                c -> {
                    try (var s =
                            c.prepareStatement(
                                    "SELECT principal,identified FROM a2a_lite_owners WHERE"
                                            + " task_id=?")) {
                        s.setString(1, id);
                        try (var row = s.executeQuery()) {
                            return row.next()
                                    && row.getString(1).equals(TaskOwnership.principal(context))
                                    && row.getBoolean(2) == context.getUser().isAuthenticated();
                        }
                    }
                });
    }

    @Override
    public boolean isTaskRecorded(String id) {
        return transaction(
                c -> {
                    try (var s =
                            c.prepareStatement("SELECT 1 FROM a2a_lite_owners WHERE task_id=?")) {
                        s.setString(1, id);
                        try (var row = s.executeQuery()) {
                            return row.next();
                        }
                    }
                });
    }

    @Override
    public void recordOwnership(ServerCallContext context, String id, TaskOperation operation) {
        if (!context.getUser().isAuthenticated()) throw new TaskNotFoundError();
        transaction(
                c -> {
                    try (var s =
                            c.prepareStatement(
                                    "INSERT INTO a2a_lite_owners(task_id,principal,identified)"
                                            + " VALUES (?,?,?) ON CONFLICT(task_id) DO NOTHING")) {
                        s.setString(1, id);
                        s.setString(2, TaskOwnership.principal(context));
                        s.setBoolean(3, true);
                        s.executeUpdate();
                    }
                    try (var s =
                            c.prepareStatement(
                                    "SELECT principal,identified FROM a2a_lite_owners WHERE"
                                            + " task_id=?")) {
                        s.setString(1, id);
                        try (var row = s.executeQuery()) {
                            if (!row.next()
                                    || !row.getBoolean(2)
                                    || !TaskOwnership.principal(context).equals(row.getString(1)))
                                throw new TaskNotFoundError();
                        }
                    }
                    return null;
                });
    }

    @Override
    public void messageDelivered(String taskId) {
        executions.messageDelivered(taskId);
        coordination.messageDelivered(taskId);
    }

    @Override
    public Task cancelTask(ServerCallContext context, CancelTaskParams params) {
        var claim = executions.snapshot(params.id());
        Task canceled =
                transaction(
                        c -> {
                            try (var owner =
                                    c.prepareStatement(
                                            "SELECT principal,identified FROM a2a_lite_owners WHERE"
                                                + " task_id=? FOR UPDATE")) {
                                owner.setString(1, params.id());
                                try (var row = owner.executeQuery()) {
                                    if (!row.next()
                                            || !row.getString(1)
                                                    .equals(TaskOwnership.principal(context))
                                            || row.getBoolean(2)
                                                    != context.getUser().isAuthenticated())
                                        throw new TaskNotFoundError();
                                }
                            }
                            Task task;
                            try (var query =
                                    c.prepareStatement(
                                            "SELECT payload FROM a2a_lite_tasks WHERE task_id=?")) {
                                query.setString(1, params.id());
                                try (var row = query.executeQuery()) {
                                    if (!row.next()) throw new TaskNotFoundError();
                                    task = decode(row.getString(1), Task.class);
                                }
                            }
                            if (task.status().state().isFinal()) throw new TaskNotCancelableError();
                            Task result =
                                    Task.builder(task)
                                            .status(new TaskStatus(TaskState.TASK_STATE_CANCELED))
                                            .build();
                            // Only this authorized, locked control-plane transition bypasses an
                            // execution fence.
                            persistTask(c, result, false, true);
                            return result;
                        });
        executions.committed(canceled, claim);
        return canceled;
    }

    @Override
    public void prepareContinuation(ServerCallContext context, String taskId) {
        if (!owns(context, taskId)) throw new TaskNotFoundError();
        Task task = get(taskId);
        if (task == null) throw new TaskNotFoundError();
        if (task.status().state().isFinal()) throw new InvalidParamsError("Task is finalized");
        executions.prepare(taskId);
    }

    @Override
    public void save(Task task, boolean replicated) {
        var claim = executions.snapshot(task.id());
        transaction(
                c -> {
                    persistTask(c, task, replicated, false);
                    return null;
                });
        executions.committed(task, claim);
    }

    void persistTask(Connection c, Task task, boolean replicated, boolean reconciliation)
            throws SQLException {
        task = com.a2alite.server.TaskBounds.retain(task, limits);
        String payload = encode(task);
        if (payload.getBytes(java.nio.charset.StandardCharsets.UTF_8).length
                > limits.maxRequestBytes() + limits.maxResultBytes() + 65536L)
            throw new IllegalArgumentException("Stored task size limit exceeded");
        lockOwner(c, task.id());
        executions.validateWriter(c, task, reconciliation);
        long revision = 1;
        try (var s =
                c.prepareStatement(
                        "SELECT revision,finalized,state FROM a2a_lite_tasks WHERE task_id=?")) {
            s.setString(1, task.id());
            try (var row = s.executeQuery()) {
                if (row.next()) {
                    revision = row.getLong(1) + 1;
                    if (row.getBoolean(2) && !row.getString(3).equals(task.status().state().name()))
                        throw new IllegalStateException("Finalized task cannot change state");
                }
            }
        }
        try (var s =
                c.prepareStatement(
                        "INSERT INTO"
                            + " a2a_lite_tasks(task_id,payload,revision,context_id,state,updated_at,finalized)"
                            + " VALUES (?,?,?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET"
                            + " payload=EXCLUDED.payload,revision=EXCLUDED.revision,context_id=EXCLUDED.context_id,state=EXCLUDED.state,updated_at=EXCLUDED.updated_at,finalized=EXCLUDED.finalized")) {
            s.setString(1, task.id());
            s.setString(2, payload);
            s.setLong(3, revision);
            s.setString(4, task.contextId());
            s.setString(5, task.status().state().name());
            s.setLong(6, task.status().timestamp().toInstant().toEpochMilli());
            s.setBoolean(7, task.status().state().isFinal());
            s.executeUpdate();
        }
        try (var journal =
                c.prepareStatement(
                        "INSERT INTO a2a_lite_events(task_id,revision,payload) VALUES (?,?,?)")) {
            journal.setString(1, task.id());
            journal.setLong(2, revision);
            journal.setString(3, payload);
            journal.executeUpdate();
        }
        if (!replicated) {
            try (var s =
                    c.prepareStatement("SELECT config_id FROM a2a_lite_push WHERE task_id=?")) {
                s.setString(1, task.id());
                try (var rows = s.executeQuery()) {
                    while (rows.next()) {
                        String config = rows.getString(1);
                        try (var insert =
                                c.prepareStatement(
                                        "INSERT INTO"
                                            + " a2a_lite_outbox(event_id,task_id,config_id,revision,payload)"
                                            + " VALUES (?,?,?,?,?)")) {
                            insert.setString(1, UUID.randomUUID().toString());
                            insert.setString(2, task.id());
                            insert.setString(3, config);
                            insert.setLong(4, revision);
                            insert.setString(5, eventJson(task));
                            insert.executeUpdate();
                        }
                    }
                }
            }
        }
        executions.afterSave(c, task, reconciliation);
    }

    static void lockOwner(Connection c, String id) throws SQLException {
        try (var s =
                c.prepareStatement(
                        "SELECT task_id FROM a2a_lite_owners WHERE task_id=? FOR UPDATE")) {
            s.setString(1, id);
            try (var row = s.executeQuery()) {
                if (!row.next()) throw new TaskNotFoundError();
            }
        }
    }

    @Override
    public Task get(String id) {
        return transaction(
                c -> {
                    try (var s =
                            c.prepareStatement(
                                    "SELECT payload FROM a2a_lite_tasks WHERE task_id=?")) {
                        s.setString(1, id);
                        try (var row = s.executeQuery()) {
                            return row.next() ? decode(row.getString(1), Task.class) : null;
                        }
                    }
                });
    }

    @Override
    public void delete(String id) {
        transaction(
                c -> {
                    try (var s =
                            c.prepareStatement("DELETE FROM a2a_lite_owners WHERE task_id=?")) {
                        s.setString(1, id);
                        s.executeUpdate();
                    }
                    return null;
                });
    }

    @Override
    public boolean isTaskFinalized(String id) {
        Task task = get(id);
        return task != null && task.status().state().isFinal();
    }

    @Override
    public boolean isTaskActive(String id) {
        Task task = get(id);
        return task != null
                && (!task.status().state().isFinal()
                        || task.status()
                                .timestamp()
                                .toInstant()
                                .plusSeconds(30)
                                .isAfter(Instant.now()));
    }

    @Override
    public ListTasksResult list(ListTasksParams params, ServerCallContext context) {
        if (context == null) return new ListTasksResult(List.of(), 0, 0, null);
        return transaction(
                c -> {
                    // Filter authorization in SQL before ordering/pagination, including tenant in
                    // principal.
                    String where =
                            " FROM a2a_lite_tasks t JOIN a2a_lite_owners o ON t.task_id=o.task_id"
                                    + " WHERE o.principal=? AND o.identified=?";
                    var values = new ArrayList<Object>();
                    values.add(TaskOwnership.principal(context));
                    values.add(context.getUser().isAuthenticated());
                    if (params.contextId() != null) {
                        where += " AND t.context_id=?";
                        values.add(params.contextId());
                    }
                    if (params.status() != null) {
                        where += " AND t.state=?";
                        values.add(params.status().name());
                    }
                    if (params.statusTimestampAfter() != null) {
                        where += " AND t.updated_at>?";
                        values.add(params.statusTimestampAfter().toEpochMilli());
                    }
                    int count;
                    try (var s = c.prepareStatement("SELECT COUNT(*)" + where)) {
                        bind(s, values);
                        try (var rows = s.executeQuery()) {
                            rows.next();
                            count = rows.getInt(1);
                        }
                    }
                    if (params.pageToken() != null && !params.pageToken().isEmpty()) {
                        try {
                            String decoded =
                                    new String(
                                            Base64.getUrlDecoder().decode(params.pageToken()),
                                            java.nio.charset.StandardCharsets.UTF_8);
                            int split = decoded.indexOf(':');
                            long time = Long.parseLong(decoded.substring(0, split));
                            String id = decoded.substring(split + 1);
                            where += " AND (t.updated_at<? OR (t.updated_at=? AND t.task_id>?))";
                            values.add(time);
                            values.add(time);
                            values.add(id);
                        } catch (RuntimeException e) {
                            throw new InvalidParamsError("Invalid page token");
                        }
                    }
                    int size = Math.min(params.getEffectivePageSize(), limits.maxHistoryLength());
                    var tasks = new ArrayList<Task>();
                    try (var s =
                            c.prepareStatement(
                                    "SELECT t.payload"
                                            + where
                                            + " ORDER BY t.updated_at DESC,t.task_id LIMIT ?")) {
                        values.add(size + 1);
                        bind(s, values);
                        try (var rows = s.executeQuery()) {
                            while (rows.next()) tasks.add(decode(rows.getString(1), Task.class));
                        }
                    }
                    String token = null;
                    if (tasks.size() > size) {
                        tasks.remove(tasks.size() - 1);
                        Task last = tasks.get(tasks.size() - 1);
                        token =
                                Base64.getUrlEncoder()
                                        .withoutPadding()
                                        .encodeToString(
                                                (last.status()
                                                                        .timestamp()
                                                                        .toInstant()
                                                                        .toEpochMilli()
                                                                + ":"
                                                                + last.id())
                                                        .getBytes(
                                                                java.nio.charset.StandardCharsets
                                                                        .UTF_8));
                    }
                    var transformed = new ArrayList<Task>();
                    for (Task task : tasks) {
                        var builder = Task.builder(task);
                        var history = task.history();
                        int n =
                                Math.min(
                                        params.getEffectiveHistoryLength(),
                                        limits.maxHistoryLength());
                        if (history != null)
                            builder.history(
                                    history.subList(
                                            Math.max(0, history.size() - n), history.size()));
                        if (!params.shouldIncludeArtifacts()) builder.artifacts(List.of());
                        transformed.add(builder.build());
                    }
                    return new ListTasksResult(transformed, count, transformed.size(), token);
                });
    }

    @Override
    public TaskPushNotificationConfig setInfo(TaskPushNotificationConfig config) {
        return setInfo(config, "1.0");
    }

    @Override
    public TaskPushNotificationConfig setInfo(TaskPushNotificationConfig original, String version) {
        boolean omitted = original.id() == null || original.id().isEmpty();
        String id = omitted ? original.taskId() : original.id();
        var config = TaskPushNotificationConfig.builder(original).id(id).build();
        return transaction(
                c -> {
                    lockOwner(c, config.taskId());
                    int count = 0;
                    boolean exists = false;
                    try (var s =
                            c.prepareStatement(
                                    "SELECT config_id FROM a2a_lite_push WHERE task_id=?")) {
                        s.setString(1, config.taskId());
                        try (var rows = s.executeQuery()) {
                            while (rows.next()) {
                                count++;
                                exists |= id.equals(rows.getString(1));
                            }
                        }
                    }
                    if (omitted && exists)
                        throw new InvalidParamsError("Default callback config already exists");
                    if (!exists && count >= limits.maxPushConfigsPerTask())
                        throw new InvalidParamsError("Push configuration limit exceeded");
                    try (var s =
                            c.prepareStatement(
                                    "INSERT INTO"
                                        + " a2a_lite_push(task_id,config_id,encrypted,protocol)"
                                        + " VALUES (?,?,?,?) ON CONFLICT(task_id,config_id) DO"
                                        + " UPDATE SET"
                                        + " encrypted=EXCLUDED.encrypted,protocol=EXCLUDED.protocol")) {
                        s.setString(1, config.taskId());
                        s.setString(2, id);
                        s.setString(3, keyring.encrypt(encode(config), config.taskId(), id));
                        s.setString(4, version == null ? "1.0" : version);
                        s.executeUpdate();
                    }
                    // Fast tasks may finish before SDK registration reaches this store. Catch up
                    // with
                    // the current committed snapshot in the same transaction as the configuration.
                    try (var enqueue =
                            c.prepareStatement(
                                    "INSERT INTO"
                                        + " a2a_lite_outbox(event_id,task_id,config_id,revision,payload)"
                                        + " SELECT ?,task_id,?,revision,? FROM a2a_lite_tasks WHERE"
                                        + " task_id=? ON CONFLICT(task_id,config_id,revision) DO"
                                        + " NOTHING")) {
                        Task current = null;
                        try (var select =
                                c.prepareStatement(
                                        "SELECT payload FROM a2a_lite_tasks WHERE task_id=?")) {
                            select.setString(1, config.taskId());
                            try (var row = select.executeQuery()) {
                                if (row.next()) current = decode(row.getString(1), Task.class);
                            }
                        }
                        if (current != null) {
                            enqueue.setString(1, UUID.randomUUID().toString());
                            enqueue.setString(2, id);
                            enqueue.setString(3, eventJson(current));
                            enqueue.setString(4, config.taskId());
                            enqueue.executeUpdate();
                        }
                    }
                    return config;
                });
    }

    @Override
    public ListTaskPushNotificationConfigsResult getInfo(
            ListTaskPushNotificationConfigsParams params) {
        return transaction(
                c -> {
                    var configs = new ArrayList<TaskPushNotificationConfig>();
                    try (var s =
                            c.prepareStatement(
                                    "SELECT config_id,encrypted FROM a2a_lite_push WHERE task_id=?"
                                            + " AND config_id>=? ORDER BY config_id")) {
                        s.setString(1, params.id());
                        s.setString(2, params.pageToken() == null ? "" : params.pageToken());
                        try (var rows = s.executeQuery()) {
                            while (rows.next())
                                configs.add(
                                        decode(
                                                keyring.decrypt(
                                                        rows.getString(2),
                                                        params.id(),
                                                        rows.getString(1)),
                                                TaskPushNotificationConfig.class));
                        }
                    }
                    String token = null;
                    int n = params.pageSize();
                    if (n > 0 && configs.size() > n) {
                        token = configs.get(n).id();
                        configs = new ArrayList<>(configs.subList(0, n));
                    }
                    return new ListTaskPushNotificationConfigsResult(configs, token);
                });
    }

    @Override
    public void deleteInfo(String task, String config) {
        transaction(
                c -> {
                    lockOwner(c, task);
                    try (var s =
                            c.prepareStatement(
                                    "DELETE FROM a2a_lite_push WHERE task_id=? AND config_id=?")) {
                        s.setString(1, task);
                        s.setString(2, config == null ? task : config);
                        s.executeUpdate();
                    }
                    return null;
                });
    }

    @Override
    public String getProtocolVersion(String task, String config) {
        return transaction(
                c -> {
                    try (var s =
                            c.prepareStatement(
                                    "SELECT protocol FROM a2a_lite_push WHERE task_id=? AND"
                                            + " config_id=?")) {
                        s.setString(1, task);
                        s.setString(2, config);
                        try (var rows = s.executeQuery()) {
                            return rows.next() ? rows.getString(1) : "1.0";
                        }
                    }
                });
    }

    /**
     * Operator retention: remove a bounded batch only after every delivery is acknowledged. Dead
     * letters intentionally block deletion until an operator retries or resolves them.
     */
    public int purgeFinalizedBefore(Instant cutoff, int batchSize) {
        Objects.requireNonNull(cutoff);
        if (batchSize < 1 || batchSize > 10_000)
            throw new IllegalArgumentException("Retention batch must be 1..10000");
        return transaction(
                c -> {
                    var ids = new ArrayList<String>();
                    try (var select =
                            c.prepareStatement(
                                    "SELECT o.task_id FROM a2a_lite_owners o JOIN a2a_lite_tasks t"
                                        + " ON o.task_id=t.task_id WHERE t.finalized AND"
                                        + " t.updated_at<? AND NOT EXISTS (SELECT 1 FROM"
                                        + " a2a_lite_outbox delivery WHERE"
                                        + " delivery.task_id=t.task_id AND NOT delivery.delivered)"
                                        + " LIMIT ? FOR UPDATE OF o SKIP LOCKED")) {
                        select.setLong(1, cutoff.toEpochMilli());
                        select.setInt(2, batchSize);
                        try (var rows = select.executeQuery()) {
                            while (rows.next()) ids.add(rows.getString(1));
                        }
                    }
                    for (String id : ids)
                        try (var delete =
                                c.prepareStatement("DELETE FROM a2a_lite_owners WHERE task_id=?")) {
                            delete.setString(1, id);
                            delete.executeUpdate();
                        }
                    return ids.size();
                });
    }

    private static String encode(Object value) {
        try {
            return JsonUtil.toJson(value);
        } catch (Exception e) {
            throw new IllegalStateException("Task serialization failed", e);
        }
    }

    private static String eventJson(Task task) {
        try {
            return JsonUtil.toJsonStreamingEvent(task);
        } catch (Exception e) {
            throw new IllegalStateException("Task serialization failed", e);
        }
    }

    static <T> T decode(String value, Class<T> type) {
        try {
            return JsonUtil.fromJson(value, type);
        } catch (Exception e) {
            throw new IllegalStateException("Persisted record is invalid", e);
        }
    }

    static void bind(PreparedStatement statement, List<Object> values) throws SQLException {
        for (int i = 0; i < values.size(); i++) statement.setObject(i + 1, values.get(i));
    }

    interface Work<T> {
        T apply(Connection connection) throws SQLException;
    }

    <T> T transaction(Work<T> work) {
        try (var c = source.getConnection()) {
            c.setAutoCommit(false);
            try {
                T value = work.apply(c);
                c.commit();
                return value;
            } catch (SQLException | RuntimeException e) {
                c.rollback();
                throw e;
            }
        } catch (SQLException e) {
            throw new IllegalStateException("Protocol persistence operation failed", e);
        }
    }
}
