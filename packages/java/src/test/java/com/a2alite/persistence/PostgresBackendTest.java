package com.a2alite.persistence;

import static org.assertj.core.api.Assertions.*;

import com.a2alite.*;
import com.a2alite.auth.*;
import com.a2alite.runtime.*;
import com.a2alite.server.TaskOwnership;

import org.a2aproject.sdk.server.ServerCallContext;
import org.a2aproject.sdk.server.auth.*;
import org.a2aproject.sdk.spec.*;
import org.a2aproject.sdk.spec.Task;
import org.a2aproject.sdk.spec.TaskState;
import org.a2aproject.sdk.spec.TaskStatus;
import org.junit.jupiter.api.*;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.postgresql.ds.PGSimpleDataSource;

import java.time.Duration;
import java.util.*;
import java.util.concurrent.*;

import javax.crypto.spec.SecretKeySpec;

@EnabledIfEnvironmentVariable(named = "A2ALITE_POSTGRES_DSN", matches = ".+")
class PostgresBackendTest {
    private PGSimpleDataSource source;
    private JdbcProtocolBackend backend;
    private String schema;
    private final CallbackKeyring keyring =
            new CallbackKeyring("test", Map.of("test", new SecretKeySpec(new byte[32], "AES")));

    @BeforeEach
    void setup() throws Exception {
        source = new PGSimpleDataSource();
        source.setURL(System.getenv("A2ALITE_POSTGRES_DSN"));
        source.setUser(System.getenv("A2ALITE_POSTGRES_USER"));
        source.setPassword(System.getenv("A2ALITE_POSTGRES_PASSWORD"));
        schema = "java_test_" + UUID.randomUUID().toString().replace("-", "");
        try (var c = source.getConnection();
                var s = c.createStatement()) {
            s.execute("CREATE SCHEMA " + schema);
        }
        source.setCurrentSchema(schema);
        backend = new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults());
        backend.initializeSchema();
    }

    @AfterEach
    void cleanup() throws Exception {
        if (backend != null) backend.close();
        if (source != null) {
            try (var c = source.getConnection();
                    var s = c.createStatement()) {
                s.execute("DROP SCHEMA " + schema + " CASCADE");
            }
        }
    }

    private ServerCallContext context(String user, String tenant) {
        return new ServerCallContext(
                new AuthenticatedUser(user), Map.of(TaskOwnership.TENANT_KEY, tenant), Set.of());
    }

    private Task task(String id, TaskState state) {
        return Task.builder().id(id).contextId("ctx").status(new TaskStatus(state)).build();
    }

    private void seed(String id) {
        backend.recordOwnership(context("alice", ""), id, TaskOperation.MESSAGE_SEND);
        backend.save(task(id, TaskState.TASK_STATE_WORKING), false);
    }

    private TaskPushNotificationConfig config(String task, String id) {
        return TaskPushNotificationConfig.builder()
                .taskId(task)
                .id(id)
                .url("https://example.com/callback")
                .token("secret-token")
                .build();
    }

    @Test
    void restartPreservesOwnerAndFiltersBeforePagination() {
        seed("alice-task");
        backend.recordOwnership(context("bob", ""), "bob-task", TaskOperation.MESSAGE_SEND);
        backend.save(task("bob-task", TaskState.TASK_STATE_COMPLETED), false);
        backend.recordOwnership(context("alice", "blue"), "blue-task", TaskOperation.MESSAGE_SEND);
        backend.save(task("blue-task", TaskState.TASK_STATE_COMPLETED), false);
        var restarted = new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults());
        assertThat(restarted.get("alice-task").id()).isEqualTo("alice-task");
        assertThat(restarted.checkRead(context("bob", ""), "alice-task", TaskOperation.GET_TASK))
                .isFalse();
        assertThat(
                        restarted.checkRead(
                                context("alice", "blue"), "alice-task", TaskOperation.GET_TASK))
                .isFalse();
        var list =
                restarted.list(
                        new ListTasksParams(null, null, 1, null, null, null, null, null),
                        context("alice", ""));
        assertThat(list.tasks()).extracting(Task::id).containsExactly("alice-task");
        assertThat(list.totalSize()).isEqualTo(1);
    }

    @Test
    void taskAndOutboxRollbackTogetherThenRetryWithStableDeliveryId() throws Exception {
        seed("atomic");
        backend.setInfo(config("atomic", "hook"));
        assertThat(backend.outbox().drainOnce((url, payload, headers) -> {})).isEqualTo(1);
        try (var c = source.getConnection();
                var s = c.createStatement()) {
            s.execute(
                    "CREATE FUNCTION reject_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN"
                            + " RAISE EXCEPTION 'injected commit failure'; END $$");
            s.execute(
                    "CREATE TRIGGER reject_outbox BEFORE INSERT ON a2a_lite_outbox FOR EACH ROW"
                            + " EXECUTE FUNCTION reject_outbox()");
        }
        assertThatThrownBy(
                        () -> backend.save(task("atomic", TaskState.TASK_STATE_COMPLETED), false))
                .hasMessageContaining("persistence");
        assertThat(backend.get("atomic").status().state()).isEqualTo(TaskState.TASK_STATE_WORKING);
        assertThat(backend.outbox().metrics().get("pending")).isZero();
        try (var c = source.getConnection();
                var s = c.createStatement()) {
            s.execute("DROP TRIGGER reject_outbox ON a2a_lite_outbox");
        }
        backend.save(task("atomic", TaskState.TASK_STATE_COMPLETED), false);
        var ids = new ArrayList<String>();
        assertThat(
                        backend.outbox()
                                .drainOnce(
                                        (url, payload, headers) -> {
                                            ids.add(headers.get("X-A2A-Delivery-Id"));
                                            throw new java.io.IOException("retry");
                                        }))
                .isZero();
        try (var c = source.getConnection();
                var s = c.createStatement()) {
            s.execute("UPDATE a2a_lite_outbox SET next_at=0");
        }
        assertThat(
                        backend.outbox()
                                .drainOnce(
                                        (url, payload, headers) -> {
                                            ids.add(headers.get("X-A2A-Delivery-Id"));
                                            assertThat(payload)
                                                    .contains("task", "TASK_STATE_COMPLETED");
                                        }))
                .isEqualTo(1);
        assertThat(ids).hasSize(2);
        assertThat(ids.get(0)).isEqualTo(ids.get(1));
        assertThat(backend.outbox().metrics().get("delivered")).isEqualTo(2);
    }

    @Test
    void replicaClaimsAndExpiredAcknowledgmentsAreFenced() throws Exception {
        seed("leased");
        backend.setInfo(config("leased", "hook"));
        backend.save(task("leased", TaskState.TASK_STATE_COMPLETED), false);
        var replica = new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults());
        var first = backend.outbox().claim();
        assertThat(first).isNotNull();
        assertThat(replica.outbox().claim()).isNull();
        try (var c = source.getConnection();
                var s = c.createStatement()) {
            s.execute("UPDATE a2a_lite_outbox SET lease_until=0");
        }
        var retry = replica.outbox().claim();
        assertThat(retry.id()).isEqualTo(first.id());
        assertThat(retry.token()).isNotEqualTo(first.token());
        assertThat(backend.outbox().finish(first, true)).isFalse();
        assertThat(replica.outbox().finish(retry, true)).isTrue();
    }

    @Test
    void encryptedCallbacksRotateKeysAndDeletionCancelsQueuedWork() throws Exception {
        seed("encrypted");
        backend.setInfo(config("encrypted", "hook"));
        backend.save(task("encrypted", TaskState.TASK_STATE_COMPLETED), false);
        String encrypted;
        try (var c = source.getConnection();
                var s = c.createStatement();
                var row = s.executeQuery("SELECT encrypted FROM a2a_lite_push")) {
            row.next();
            encrypted = row.getString(1);
        }
        assertThat(encrypted).doesNotContain("secret-token", "example.com");
        assertThatThrownBy(() -> keyring.decrypt(encrypted, "another-task", "hook"))
                .hasMessageContaining("decryption");
        var rotated =
                new CallbackKeyring(
                        "new",
                        Map.of(
                                "test",
                                new SecretKeySpec(new byte[32], "AES"),
                                "new",
                                new SecretKeySpec(new byte[16], "AES")));
        var replica = new JdbcProtocolBackend(source, rotated, RuntimeLimits.defaults());
        assertThat(
                        replica.getInfo(new ListTaskPushNotificationConfigsParams("encrypted"))
                                .configs()
                                .get(0)
                                .token())
                .isEqualTo("secret-token");
        replica.setInfo(config("encrypted", "hook"));
        try (var c = source.getConnection();
                var s = c.createStatement();
                var row = s.executeQuery("SELECT encrypted FROM a2a_lite_push")) {
            row.next();
            assertThat(row.getString(1)).startsWith("new.");
        }
        replica.deleteInfo("encrypted", "hook");
        assertThat(replica.outbox().metrics().get("pending")).isZero();
    }

    @Test
    void checkpointRecoveryAcrossReplicasRejectsStaleWriter() throws Exception {
        var first = backend.checkpoints();
        var second =
                new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults()).checkpoints();
        first.create("job", "step-0");
        var lease = first.claim("job", "replica-a", Duration.ofSeconds(30));
        assertThat(second.claim("job", "replica-b", Duration.ofSeconds(30))).isNull();
        first.checkpoint(lease, "step-1", Duration.ofSeconds(30), false);
        try (var c = source.getConnection();
                var s = c.createStatement()) {
            s.execute("UPDATE a2a_lite_checkpoints SET lease_until=0");
        }
        var takeover = second.claim("job", "replica-b", Duration.ofSeconds(30));
        assertThat(takeover.checkpoint()).isEqualTo("step-1");
        assertThat(takeover.fence()).isGreaterThan(lease.fence());
        assertThatThrownBy(() -> first.checkpoint(lease, "corrupt", Duration.ofSeconds(30), true))
                .hasMessageContaining("Stale");
        second.checkpoint(takeover, "step-2", Duration.ofSeconds(30), true);
        assertThat(first.claim("job", "replica-a", Duration.ofSeconds(30))).isNull();
    }

    @Test
    void otherReplicaSubscribesAndCancelsLiveTaskWithoutAllowingStaleCompletion() throws Exception {
        var stopped = new CountDownLatch(1);
        var auth =
                new APIKeyAuth(
                        Map.of(
                                "alice",
                                AuthResult.success("alice"),
                                "bob",
                                AuthResult.success("bob")));
        var one =
                Agent.builder()
                        .name("replica-a")
                        .description("test")
                        .auth(auth)
                        .protocolBackend(backend)
                        .runtimeOptions(RuntimeOptions.durable())
                        .build();
        one.skill(
                "hold",
                SkillConfig.withStreaming(),
                params ->
                        com.a2alite.streaming.StreamingHandler.stream(
                                sink -> {
                                    try {
                                        for (int n = 0; n < 200; n++) {
                                            sink.accept("tick-" + n);
                                            Thread.sleep(25);
                                        }
                                    } catch (InterruptedException e) {
                                        Thread.currentThread().interrupt();
                                    } finally {
                                        stopped.countDown();
                                    }
                                }));
        var two =
                Agent.builder()
                        .name("replica-b")
                        .description("test")
                        .auth(auth)
                        .protocolBackend(
                                new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults()))
                        .runtimeOptions(RuntimeOptions.durable())
                        .build();
        var json = new com.fasterxml.jackson.databind.ObjectMapper();
        try (var a = one.start("127.0.0.1", 0);
                var b = two.start("127.0.0.1", 0)) {
            String urlA = "http://127.0.0.1:" + a.port(), urlB = "http://127.0.0.1:" + b.port();
            var http = java.net.http.HttpClient.newHttpClient();
            var send =
                    Map.of(
                            "message",
                            Map.of(
                                    "role",
                                    "ROLE_USER",
                                    "messageId",
                                    "remote",
                                    "parts",
                                    List.of(Map.of("text", "{\"skill\":\"hold\"}"))),
                            "configuration",
                            Map.of("returnImmediately", true));
            var started =
                    http.send(
                            rpc(urlA, "SendMessage", send, "alice"),
                            java.net.http.HttpResponse.BodyHandlers.ofString());
            String id =
                    json.readTree(started.body()).path("result").path("task").path("id").asText();
            assertThat(id).as(started.body()).isNotBlank();
            var denied =
                    http.send(
                            rpc(urlB, "SubscribeToTask", Map.of("id", id), "bob"),
                            java.net.http.HttpResponse.BodyHandlers.ofString());
            assertThat(json.readTree(denied.body()).has("error")).isTrue();
            var subscription =
                    http.send(
                            rpc(urlB, "SubscribeToTask", Map.of("id", id), "alice"),
                            java.net.http.HttpResponse.BodyHandlers.ofInputStream());
            try (var reader =
                    new java.io.BufferedReader(
                            new java.io.InputStreamReader(subscription.body()))) {
                String first = reader.readLine();
                assertThat(first).contains("task", id);
                var canceled =
                        http.send(
                                rpc(urlB, "CancelTask", Map.of("id", id), "alice"),
                                java.net.http.HttpResponse.BodyHandlers.ofString());
                assertThat(
                                json.readTree(canceled.body())
                                        .path("result")
                                        .path("status")
                                        .path("state")
                                        .asText())
                        .as(canceled.body())
                        .isEqualTo("TASK_STATE_CANCELED");
                assertThat(stopped.await(3, TimeUnit.SECONDS)).isTrue();
                assertThat(reader.lines().reduce("", (left, right) -> left + right))
                        .contains("TASK_STATE_CANCELED");
            }
            assertThat(backend.get(id).status().state()).isEqualTo(TaskState.TASK_STATE_CANCELED);
            assertThatThrownBy(() -> backend.save(task(id, TaskState.TASK_STATE_COMPLETED), false))
                    .hasMessageContaining("Stale");
        }
    }

    private java.net.http.HttpRequest rpc(
            String url, String method, Map<String, ?> params, String key) throws Exception {
        return java.net.http.HttpRequest.newBuilder(java.net.URI.create(url))
                .timeout(Duration.ofSeconds(10))
                .header("A2A-Version", "1.0")
                .header("X-API-Key", key)
                .header("Content-Type", "application/json")
                .POST(
                        java.net.http.HttpRequest.BodyPublishers.ofString(
                                new com.fasterxml.jackson.databind.ObjectMapper()
                                        .writeValueAsString(
                                                Map.of(
                                                        "jsonrpc", "2.0", "id", 1, "method", method,
                                                        "params", params))))
                .build();
    }

    @Test
    void staleProducerCannotCancelSuccessorButAuthorizedControlPlaneCan() throws Exception {
        seed("takeover");
        backend.executions.claim("takeover");
        try (var c = source.getConnection();
                var statement = c.createStatement()) {
            statement.execute(
                    "UPDATE a2a_lite_owners SET execution_until=1 WHERE task_id='takeover'");
        }
        var successor = new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults());
        successor.executions.claim("takeover");
        successor.save(task("takeover", TaskState.TASK_STATE_WORKING), false);
        assertThatThrownBy(
                        () -> backend.save(task("takeover", TaskState.TASK_STATE_CANCELED), false))
                .hasMessageContaining("Stale");
        assertThat(successor.get("takeover").status().state())
                .isEqualTo(TaskState.TASK_STATE_WORKING);
        var request = new CancelTaskParams("takeover", null, Map.of());
        assertThatThrownBy(() -> backend.cancelTask(context("bob", ""), request))
                .isInstanceOf(TaskNotFoundError.class);
        assertThat(backend.cancelTask(context("alice", ""), request).status().state())
                .isEqualTo(TaskState.TASK_STATE_CANCELED);
        assertThatThrownBy(
                        () ->
                                successor.save(
                                        task("takeover", TaskState.TASK_STATE_COMPLETED), false))
                .hasMessageContaining("Stale");
    }

    @Test
    void expiredOrdinaryExecutionBecomesFailedAndFencesOriginalWriter() throws Exception {
        seed("crashed");
        backend.executions.claim("crashed");
        backend.setInfo(config("crashed", "hook"));
        try (var c = source.getConnection();
                var statement = c.createStatement()) {
            statement.execute(
                    "UPDATE a2a_lite_owners SET execution_until=1 WHERE task_id='crashed'");
        }
        var replica = new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults());
        assertThat(replica.executions.reconcileExpired()).isEqualTo(1);
        assertThat(replica.get("crashed").status().state()).isEqualTo(TaskState.TASK_STATE_FAILED);
        assertThat(replica.outbox().metrics().get("pending")).isEqualTo(2);
        assertThatThrownBy(
                        () -> backend.save(task("crashed", TaskState.TASK_STATE_COMPLETED), false))
                .hasMessageContaining("Stale");
        assertThat(backend.executions.renew("crashed")).isFalse();
    }

    @Test
    void retentionProtectsUndeliveredCallbacksThenRemovesTheWholeTaskBoundary() {
        seed("retained");
        backend.save(task("retained", TaskState.TASK_STATE_COMPLETED), false);
        backend.setInfo(config("retained", "hook"));
        var future = java.time.Instant.now().plusSeconds(60);
        assertThat(backend.purgeFinalizedBefore(future, 10)).isZero();
        assertThat(backend.outbox().drainOnce((url, payload, headers) -> {})).isEqualTo(1);
        assertThat(backend.purgeFinalizedBefore(future, 10)).isEqualTo(1);
        assertThat(backend.get("retained")).isNull();
        assertThat(backend.isTaskRecorded("retained")).isFalse();
        assertThat(backend.outbox().metrics().get("delivered")).isZero();
    }

    @Test
    void finalAndStatelessClaimsAreReclaimedWithoutPermittingStaleWrites() throws Exception {
        seed("finished");
        backend.executions.claim("finished");
        backend.save(task("finished", TaskState.TASK_STATE_COMPLETED), false);
        assertThat(backend.executions.retainedClaims()).isZero();
        assertThatThrownBy(
                        () -> backend.save(task("finished", TaskState.TASK_STATE_COMPLETED), false))
                .hasMessageContaining("Stale");
        backend.recordOwnership(context("alice", ""), "message-only", TaskOperation.MESSAGE_SEND);
        backend.executions.claim("message-only");
        try (var c = source.getConnection();
                var s = c.createStatement()) {
            s.execute("UPDATE a2a_lite_owners SET execution_until=1 WHERE task_id='message-only'");
        }
        backend.executions.reconcileExpired();
        assertThat(backend.executions.retainedClaims()).isZero();
        assertThat(backend.isTaskRecorded("message-only")).isFalse();
        backend.recordOwnership(
                context("alice", ""), "crashed-message", TaskOperation.MESSAGE_SEND);
        backend.executions.claim("crashed-message");
        try (var c = source.getConnection();
                var statement = c.createStatement()) {
            statement.execute(
                    "UPDATE a2a_lite_owners SET execution_until=1,created_at=1 WHERE"
                        + " task_id='crashed-message'");
        }
        var survivingReplica = new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults());
        survivingReplica.executions.reconcileExpired();
        assertThat(backend.isTaskRecorded("crashed-message")).isFalse();
        backend.executions.reconcileExpired();
        assertThat(backend.executions.retainedClaims()).isZero();
        assertThatThrownBy(
                        () ->
                                backend.save(
                                        task("message-only", TaskState.TASK_STATE_COMPLETED),
                                        false))
                .isInstanceOf(TaskNotFoundError.class);
    }

    @Test
    void interruptedTaskContinuationReservesNewFenceBeforeSdkHistorySave() {
        seed("waiting");
        backend.executions.claim("waiting");
        backend.save(task("waiting", TaskState.TASK_STATE_INPUT_REQUIRED), false);
        assertThat(backend.executions.retainedClaims()).isZero();
        assertThatThrownBy(() -> backend.save(task("waiting", TaskState.TASK_STATE_WORKING), false))
                .hasMessageContaining("Stale");
        assertThatThrownBy(() -> backend.prepareContinuation(context("bob", ""), "waiting"))
                .isInstanceOf(TaskNotFoundError.class);
        backend.prepareContinuation(context("alice", ""), "waiting");
        backend.save(
                task("waiting", TaskState.TASK_STATE_INPUT_REQUIRED), false); // SDK appends history
        backend.executions.claim("waiting");
        backend.save(task("waiting", TaskState.TASK_STATE_COMPLETED), false);
        assertThat(backend.executions.retainedClaims()).isZero();
    }

    @Test
    void crashedDeliveryClaimsAndOldDeliveriesDeadLetterBeforeAnotherSend() throws Exception {
        seed("retry-limit");
        backend.setInfo(config("retry-limit", "hook"));
        for (int attempt = 1; attempt <= DurableOutbox.MAX_ATTEMPTS; attempt++) {
            assertThat(backend.outbox().claim().attempts()).isEqualTo(attempt);
            try (var c = source.getConnection();
                    var s = c.createStatement()) {
                s.execute("UPDATE a2a_lite_outbox SET lease_until=0");
            }
        }
        assertThat(backend.outbox().claim()).isNull();
        assertThat(backend.outbox().metrics().get("dead")).isEqualTo(1);
        assertThat(backend.outbox().retryDeadLetters()).isEqualTo(1);
        var retry = backend.outbox().claim();
        assertThat(retry.attempts()).isEqualTo(1);
        backend.outbox().finish(retry, false);
        try (var c = source.getConnection();
                var s = c.createStatement()) {
            s.execute("UPDATE a2a_lite_outbox SET created_at=1,next_at=0");
        }
        assertThat(backend.outbox().claim()).isNull();
        assertThat(backend.outbox().metrics().get("dead")).isEqualTo(1);
    }

    @Test
    void httpRestartRetainsRealTaskAndRotatedPrincipal() throws Exception {
        String id;
        String pausedId;
        SkillHandlerWithContext pause =
                (params, task) -> {
                    if (Boolean.TRUE.equals(params.get("resume"))) return "resumed";
                    task.update(com.a2alite.TaskState.INPUT_REQUIRED, "Resume explicitly", null);
                    return "paused";
                };
        var auth =
                new APIKeyAuth(
                        Map.of(
                                "old",
                                AuthResult.success("alice"),
                                "new",
                                AuthResult.success("alice"),
                                "bob",
                                AuthResult.success("bob")));
        var one =
                Agent.builder()
                        .name("durable")
                        .description("test")
                        .auth(auth)
                        .protocolBackend(backend)
                        .runtimeOptions(RuntimeOptions.durable())
                        .build();
        one.skill("task", (params, task) -> task.getTaskId());
        one.skill("pause", pause);
        try (var runtime = one.start("127.0.0.1", 0)) {
            String url = "http://127.0.0.1:" + runtime.port();
            var network = new AgentNetwork().withHeaders(url, Map.of("X-API-Key", "old"));
            var handle = network.callRemoteSkillWithHandle(url, "task", Map.of(), 5);
            id = handle.getTaskId();
            assertThat(handle.getResult()).isEqualTo(id);
            var paused = network.callRemoteSkillWithHandle(url, "pause", Map.of(), 5);
            pausedId = paused.getTaskId();
            assertThat(
                            new com.fasterxml.jackson.databind.ObjectMapper()
                                    .valueToTree(paused.get())
                                    .path("status")
                                    .path("state")
                                    .asText())
                    .isEqualTo("TASK_STATE_INPUT_REQUIRED");
        }
        var two =
                Agent.builder()
                        .name("durable")
                        .description("test")
                        .auth(auth)
                        .protocolBackend(
                                new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults()))
                        .runtimeOptions(RuntimeOptions.durable())
                        .build();
        two.skill("pause", pause);
        try (var runtime = two.start("127.0.0.1", 0)) {
            String url = "http://127.0.0.1:" + runtime.port();
            var network = new AgentNetwork().withHeaders(url, Map.of("X-API-Key", "new"));
            assertThat(network.getRemoteTaskSnapshot(url, id, 5).get("id")).isEqualTo(id);
            network.withHeaders(url, Map.of("X-API-Key", "bob"));
            assertThatThrownBy(() -> network.getRemoteTaskSnapshot(url, id, 5))
                    .isInstanceOf(com.a2alite.errors.RemoteAgentException.class);
            var json = new com.fasterxml.jackson.databind.ObjectMapper();
            String resume =
                    json.writeValueAsString(
                            Map.of(
                                    "jsonrpc",
                                    "2.0",
                                    "id",
                                    1,
                                    "method",
                                    "SendMessage",
                                    "params",
                                    Map.of(
                                            "message",
                                            Map.of(
                                                    "role",
                                                    "ROLE_USER",
                                                    "messageId",
                                                    "resume",
                                                    "taskId",
                                                    pausedId,
                                                    "parts",
                                                    List.of(
                                                            Map.of(
                                                                    "text",
                                                                    json.writeValueAsString(
                                                                            Map.of(
                                                                                    "skill",
                                                                                    "pause",
                                                                                    "params",
                                                                                    Map.of(
                                                                                            "resume",
                                                                                            true)))))))));
            for (String key : List.of("bob", "new")) {
                var response =
                        java.net.http.HttpClient.newHttpClient()
                                .send(
                                        java.net.http.HttpRequest.newBuilder(
                                                        java.net.URI.create(url))
                                                .header("Content-Type", "application/json")
                                                .header("A2A-Version", "1.0")
                                                .header("X-API-Key", key)
                                                .POST(
                                                        java.net.http.HttpRequest.BodyPublishers
                                                                .ofString(resume))
                                                .build(),
                                        java.net.http.HttpResponse.BodyHandlers.ofString());
                var value = json.readTree(response.body());
                if (key.equals("bob")) assertThat(value.has("error")).as(response.body()).isTrue();
                else {
                    assertThat(value.path("result").path("task").path("id").asText())
                            .as(response.body())
                            .isEqualTo(pausedId);
                    assertThat(
                                    value.path("result")
                                            .path("task")
                                            .path("status")
                                            .path("state")
                                            .asText())
                            .as(response.body())
                            .isEqualTo("TASK_STATE_COMPLETED");
                    assertThat(response.body()).contains("resumed");
                }
            }
        }
    }
}
