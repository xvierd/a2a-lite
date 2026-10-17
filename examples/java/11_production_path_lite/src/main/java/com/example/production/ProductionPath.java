package com.example.production;

import com.a2alite.*;
import com.a2alite.auth.*;
import com.a2alite.persistence.*;
import com.a2alite.runtime.*;
import com.a2alite.streaming.StreamingHandler;

import org.postgresql.ds.PGSimpleDataSource;

import java.time.Duration;
import java.util.*;

import javax.crypto.spec.SecretKeySpec;

/** One runnable progression: message -> real task -> stream -> authentication -> durable state. */
public final class ProductionPath {
    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "learning" : args[0];
        if (mode.equals("client")) {
            client(args.length > 1 ? args[1] : "http://127.0.0.1:8787");
            return;
        }
        if (mode.equals("checkpoint")) {
            checkpointDemo();
            return;
        }
        if (!Set.of("learning", "authenticated", "durable").contains(mode))
            throw new IllegalArgumentException(
                    "Use learning, authenticated, durable, checkpoint or client");
        var builder =
                Agent.builder()
                        .name("ProductionPath")
                        .description("Learn each operational boundary explicitly");
        if (!mode.equals("learning")) {
            var subject =
                    AuthResult.identified("example-service", "learner", Set.of(""), Set.of("work"));
            var keys = new HashMap<String, AuthResult>();
            keys.put(required("A2A_API_KEY"), subject);
            String rotated = System.getenv("A2A_NEXT_API_KEY");
            if (rotated != null) keys.put(rotated, subject);
            builder.auth(new APIKeyAuth(keys)).runtimeOptions(RuntimeOptions.authenticated());
        }
        if (mode.equals("durable"))
            builder.protocolBackend(database()).runtimeOptions(RuntimeOptions.durable());
        var agent = builder.build();
        agent.skill("greet", params -> "Hello, " + params.getOrDefault("name", "world"));
        agent.skill("task", (params, task) -> task.getTaskId());
        agent.skill(
                "stream",
                SkillConfig.withStreaming(),
                params -> StreamingHandler.fromIterator(List.of("one", "two", "three").iterator()));
        try (var runtime = agent.start("127.0.0.1", 8787)) {
            Runtime.getRuntime().addShutdownHook(new Thread(runtime::close));
            System.out.println(
                    "Ready: http://127.0.0.1:" + runtime.port() + "/health/ready (" + mode + ")");
            runtime.awaitTermination();
        }
    }

    private static void client(String url) throws Exception {
        var network = new AgentNetwork();
        // Evaluated on every request, including TaskHandle follow-up calls.
        if (System.getenv("A2A_API_KEY") != null)
            network.withCredentials(url, target -> Map.of("X-API-Key", required("A2A_API_KEY")));
        System.out.println(
                "Message: " + network.callRemoteSkill(url, "greet", Map.of("name", "learner"), 5));
        var handle = network.callRemoteSkillWithHandle(url, "task", Map.of(), 5);
        System.out.println("Real Task ID: " + handle.getTaskId());
        System.out.println("Task status: " + handle.get().get("status"));
        try (var stream = network.streamRemoteSkill(url, "stream", Map.of())) {
            stream.forEach(System.out::println);
        }
    }

    private static JdbcProtocolBackend database() {
        var source = new PGSimpleDataSource();
        source.setURL(required("A2ALITE_POSTGRES_DSN"));
        source.setUser(required("A2ALITE_POSTGRES_USER"));
        source.setPassword(required("A2ALITE_POSTGRES_PASSWORD"));
        source.setConnectTimeout(5);
        source.setSocketTimeout(5);
        byte[] bytes = Base64.getDecoder().decode(required("A2A_CALLBACK_KEY_BASE64"));
        var keyring =
                new CallbackKeyring("primary", Map.of("primary", new SecretKeySpec(bytes, "AES")));
        var backend = new JdbcProtocolBackend(source, keyring, RuntimeLimits.defaults());
        backend
                .initializeSchema(); // Run with a migration role in a deployed service, before
                                     // application startup.
        return backend;
    }

    private static void checkpointDemo() throws Exception {
        try (var first = database();
                var second = database()) {
            String job = UUID.randomUUID().toString();
            first.checkpoints().create(job, "step-0");
            var original = first.checkpoints().claim(job, "worker-a", Duration.ofMillis(200));
            first.checkpoints().checkpoint(original, "step-1", Duration.ofMillis(200), false);
            Thread.sleep(
                    250); // Simulate expired ownership between two independently constructed
                          // backends.
            var recovered = second.checkpoints().claim(job, "worker-b", Duration.ofSeconds(5));
            System.out.println(
                    "Recovered " + recovered.checkpoint() + "; fence=" + recovered.fence());
            second.checkpoints().checkpoint(recovered, "step-2", Duration.ofSeconds(5), true);
            try {
                first.checkpoints().checkpoint(original, "stale", Duration.ofSeconds(5), true);
            } catch (IllegalStateException expected) {
                System.out.println("Stale worker rejected.");
            }
        }
    }

    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) throw new IllegalArgumentException("Set " + name);
        return value;
    }
}
