package com.a2alite;

import com.a2alite.auth.*;
import com.a2alite.runtime.RuntimeOptions;
import com.a2alite.streaming.StreamingHandler;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.*;

/** Local interoperability gate; no external model or callback calls. */
public final class InteropFixture {
    public static void main(String[] args) throws Exception {
        var json = new ObjectMapper();
        if (args.length != 3)
            throw new IllegalArgumentException("server --port N | client --url URL");
        if (args[0].equals("server")) {
            var alice = AuthResult.success("alice");
            var builder =
                    Agent.builder()
                            .name("JavaInteroperability")
                            .description("Local protocol fixture")
                            .auth(
                                    new APIKeyAuth(
                                            Map.of(
                                                    "interop-secret",
                                                    alice,
                                                    "interop-rotated",
                                                    alice,
                                                    "interop-other",
                                                    AuthResult.success("bob"))))
                            .runtimeOptions(RuntimeOptions.authenticated());
            String database = System.getenv("A2ALITE_INTEROP_POSTGRES_DSN");
            if (database != null) {
                var source = new org.postgresql.ds.PGSimpleDataSource();
                source.setURL(database);
                source.setConnectTimeout(5);
                source.setSocketTimeout(5);
                source.setUser(System.getenv("A2ALITE_POSTGRES_USER"));
                source.setPassword(System.getenv("A2ALITE_POSTGRES_PASSWORD"));
                var key =
                        new javax.crypto.spec.SecretKeySpec(
                                new byte[32], "AES"); // Public fixture key; never production.
                var backend =
                        new com.a2alite.persistence.JdbcProtocolBackend(
                                source,
                                new com.a2alite.persistence.CallbackKeyring(
                                        "test-only", Map.of("test-only", key)),
                                com.a2alite.runtime.RuntimeLimits.defaults(),
                                false); // Never send external callbacks from this test harness.
                backend.initializeSchema();
                builder.protocolBackend(backend).runtimeOptions(RuntimeOptions.durable());
            }
            var agent = builder.build();
            agent.skill("greet", params -> params.get("text"));
            agent.skill("taskProbe", (params, task) -> task.getTaskId());
            agent.skill(
                    "pause",
                    (params, task) -> {
                        if (Boolean.TRUE.equals(params.get("resume"))) return "resumed";
                        task.update(TaskState.INPUT_REQUIRED, "Resume explicitly", null);
                        return "paused";
                    });
            agent.skill(
                    "stream",
                    SkillConfig.withStreaming(),
                    params ->
                            StreamingHandler.fromIterator(
                                    List.of("one", "two", "three").iterator()));
            agent.skill(
                    "hold",
                    SkillConfig.withStreaming(),
                    params ->
                            StreamingHandler.stream(
                                    sink -> {
                                        for (int i = 0; i < 100; i++) {
                                            sink.accept("tick-" + i);
                                            try {
                                                Thread.sleep(50);
                                            } catch (InterruptedException e) {
                                                Thread.currentThread().interrupt();
                                                break;
                                            }
                                        }
                                    }));
            agent.skill(
                    "delay",
                    params -> {
                        Thread.sleep(20);
                        return "ok";
                    });
            agent.skill(
                    "fail",
                    params -> {
                        throw new IllegalArgumentException("safe failure");
                    });
            try (var runtime = agent.start("127.0.0.1", Integer.parseInt(args[2]))) {
                Runtime.getRuntime().addShutdownHook(new Thread(runtime::close));
                System.out.println(
                        "A2A_LITE_READY "
                                + json.writeValueAsString(
                                        Map.of("url", "http://127.0.0.1:" + runtime.port())));
                runtime.awaitTermination();
            }
        } else {
            String url = args[2];
            var network =
                    new AgentNetwork().withHeaders(url, Map.of("X-API-Key", "interop-secret"));
            boolean message =
                    "hello"
                            .equals(
                                    network.callRemoteSkill(
                                            url, "greet", Map.of("text", "hello"), 10));
            var handle = network.callRemoteSkillWithHandle(url, "taskProbe", Map.of(), 10);
            boolean task = handle.getTaskId().equals(handle.getResult());
            boolean taskRead = handle.getTaskId().equals(((Map<?, ?>) handle.get()).get("id"));
            var chunks = new ArrayList<Object>();
            try (var stream = network.streamRemoteSkill(url, "stream", Map.of(), 10)) {
                stream.forEach(chunks::add);
            }
            boolean stream = chunks.equals(List.of("one", "two", "three"));
            System.out.println(
                    "A2A_LITE_RESULT "
                            + json.writeValueAsString(
                                    Map.of(
                                            "message",
                                            message,
                                            "task",
                                            task,
                                            "taskRead",
                                            taskRead,
                                            "stream",
                                            stream)));
            if (!(message && task && taskRead && stream))
                throw new AssertionError("Interoperability failed: " + chunks);
        }
    }
}
