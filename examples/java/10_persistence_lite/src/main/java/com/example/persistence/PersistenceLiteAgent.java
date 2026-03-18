package com.example.persistence;

import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import com.a2alite.push.LogPushNotifier;
import com.a2alite.push.PushNotifier;
import com.a2alite.push.WebhookPushNotifier;
import com.a2alite.tasks.InMemoryTaskStore;

import java.time.Duration;
import java.util.Map;
import java.util.logging.Level;

/**
 * PersistenceLiteAgent — pluggable TaskStore and PushNotifier.
 *
 * <p>Demonstrates how to swap notification backends between environments:
 * <ul>
 *   <li>Dev:  {@link LogPushNotifier} — events printed to the console</li>
 *   <li>Prod: {@link WebhookPushNotifier} — events POSTed to an HTTP endpoint</li>
 * </ul>
 *
 * <p>Skills:
 * <ul>
 *   <li>{@code echo}    — returns the input message unchanged</li>
 *   <li>{@code slowSum} — sums integers 1..n with a deliberate delay per step</li>
 * </ul>
 *
 * <p>Environment variables (production mode):
 * <pre>
 *   WEBHOOK_URL     URL of the webhook endpoint (required to enable webhook mode)
 *   WEBHOOK_SECRET  HMAC-SHA256 signing secret (optional; omit to disable signing)
 * </pre>
 *
 * <p>Run:
 * <pre>
 *   # Development (log to console)
 *   ./gradlew run
 *
 *   # Production (post events to a webhook)
 *   WEBHOOK_URL=https://example.com/hook WEBHOOK_SECRET=my-secret ./gradlew run
 * </pre>
 */
public class PersistenceLiteAgent {

    public static void main(String[] args) {

        // ------------------------------------------------------------------
        // 1. Choose a PushNotifier based on the environment.
        //
        //    The agent core does not care which implementation is used;
        //    swap without touching any other code.
        // ------------------------------------------------------------------
        PushNotifier notifier = buildNotifier();

        // ------------------------------------------------------------------
        // 2. Provide an explicit TaskStore.
        //
        //    InMemoryTaskStore is fine for demo purposes.
        //    Replace with a Redis or JDBC-backed implementation for production.
        // ------------------------------------------------------------------
        var taskStore = new InMemoryTaskStore();

        // ------------------------------------------------------------------
        // 3. Build the agent, wiring in both the store and notifier.
        // ------------------------------------------------------------------
        var agent = Agent.builder()
            .name("PersistenceLiteAgent")
            .description("Pluggable TaskStore + PushNotifier demo — A2A Lite")
            .version("1.0.0")
            .taskStore(taskStore)
            .pushNotifier(notifier)  // called automatically after every skill completes
            .build();

        // ------------------------------------------------------------------
        // 4. Register skills.
        // ------------------------------------------------------------------

        // echo: trivial round-trip, great for verifying the notifier fires
        agent.skill("echo",
            SkillConfig.of("Echo the input message back unchanged"),
            params -> {
                String message = (String) params.getOrDefault("message", "(empty)");
                return Map.of(
                    "skill",   "echo",
                    "message", message
                );
            }
        );

        // slowSum: simulates a long-running computation so push notifications
        // are visible while the skill is still working
        agent.skill("slowSum",
            SkillConfig.of("Sum integers 1..n with a simulated delay per step"),
            params -> {
                int n = ((Number) params.getOrDefault("n", 10)).intValue();
                long sum = 0;

                for (int i = 1; i <= n; i++) {
                    sum += i;
                    try {
                        Thread.sleep(200); // 200 ms per step — adjust as needed
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return Map.of("error", "interrupted", "partialSum", sum);
                    }
                }

                return Map.of("n", n, "sum", sum);
            }
        );

        // ------------------------------------------------------------------
        // 5. Start listening.
        // ------------------------------------------------------------------
        agent.run(8787);
    }

    // ------------------------------------------------------------------
    // Internal helpers
    // ------------------------------------------------------------------

    /**
     * Build a {@link PushNotifier} appropriate for the current environment.
     *
     * <ul>
     *   <li>If {@code WEBHOOK_URL} is set → {@link WebhookPushNotifier} (production)</li>
     *   <li>Otherwise                     → {@link LogPushNotifier}     (development)</li>
     * </ul>
     */
    private static PushNotifier buildNotifier() {
        String webhookUrl = System.getenv("WEBHOOK_URL");

        if (webhookUrl != null && !webhookUrl.isBlank()) {
            // Production: deliver events as signed HTTP POST requests
            String secret = System.getenv("WEBHOOK_SECRET"); // null → no HMAC signing

            var notifier = WebhookPushNotifier.builder()
                .url(webhookUrl)
                .secret(secret)                   // null is accepted; signing is skipped
                .maxRetries(3)                    // exponential back-off: 500 ms, 1 s, 2 s
                .timeout(Duration.ofSeconds(10))
                .build();

            System.out.println("[PersistenceLiteAgent] Notifier: WEBHOOK → " + webhookUrl
                + (secret != null ? " (HMAC signed)" : " (no signature)"));
            return notifier;
        }

        // Development: log events via java.util.logging
        var notifier = new LogPushNotifier("com.example.persistence.push", Level.INFO);
        System.out.println(
            "[PersistenceLiteAgent] Notifier: LOG  (set WEBHOOK_URL env var to use a webhook)");
        return notifier;
    }
}
