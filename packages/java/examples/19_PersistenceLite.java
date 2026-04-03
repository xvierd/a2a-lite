import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import com.a2alite.push.LogPushNotifier;
import com.a2alite.push.PushNotifier;
import com.a2alite.push.WebhookPushNotifier;
import com.a2alite.InMemoryTaskStore;

import java.time.Duration;
import java.util.Map;
import java.util.logging.Level;

/**
 * Persistence Lite — pluggable TaskStore and PushNotifier.
 *
 * Demonstrates:
 *  - Swapping push notifiers: LogPushNotifier for dev, WebhookPushNotifier for prod
 *  - Using an explicit TaskStore instance
 *  - Two skills: echo (simple) and slowSum (long-running, progress via logs)
 *
 * Run (dev mode — logs events to console):
 *   ./gradlew run -PmainClass=PersistenceLite
 *
 * Run (prod mode — posts events to a webhook, reads env vars):
 *   WEBHOOK_URL=https://example.com/hook \
 *   WEBHOOK_SECRET=my-secret \
 *   ./gradlew run -PmainClass=PersistenceLite
 */
class PersistenceLite {

    public static void main(String[] args) {

        // ----------------------------------------------------------------
        // 1. Pick a PushNotifier based on environment
        //
        //    - If WEBHOOK_URL is set → WebhookPushNotifier (production)
        //    - Otherwise             → LogPushNotifier    (development)
        // ----------------------------------------------------------------
        PushNotifier notifier = buildNotifier();

        // ----------------------------------------------------------------
        // 2. Shared, explicit TaskStore
        //
        //    Replace InMemoryTaskStore with a Redis or database-backed
        //    implementation for true persistence across restarts.
        // ----------------------------------------------------------------
        var taskStore = new InMemoryTaskStore();

        // ----------------------------------------------------------------
        // 3. Build the agent
        // ----------------------------------------------------------------
        var agent = Agent.builder()
            .name("PersistenceLiteAgent")
            .description("Shows pluggable TaskStore + PushNotifier")
            .version("1.0.0")
            .taskStore(taskStore)
            .pushNotifier(notifier)   // called after every skill completes
            .build();

        // ----------------------------------------------------------------
        // 4. Register skills
        // ----------------------------------------------------------------

        // echo — trivial round-trip, good for smoke-testing the notifier
        agent.skill("echo",
            SkillConfig.of("Echo the input message back to the caller"),
            params -> {
                String msg = (String) params.getOrDefault("message", "(empty)");
                return Map.of("echo", msg);
            }
        );

        // slowSum — simulates a long-running computation so you can watch
        //           push notifications arrive while the skill is still running
        agent.skill("slowSum",
            SkillConfig.of("Sum integers 1..n with a simulated delay per step"),
            params -> {
                int n = ((Number) params.getOrDefault("n", 10)).intValue();
                long sum = 0;
                for (int i = 1; i <= n; i++) {
                    sum += i;
                    try {
                        Thread.sleep(100); // simulate work
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return Map.of("error", "interrupted", "partialSum", sum);
                    }
                }
                return Map.of("n", n, "sum", sum);
            }
        );

        // ----------------------------------------------------------------
        // 5. Start the server
        // ----------------------------------------------------------------
        agent.run(8787);
    }

    // ----------------------------------------------------------------
    // Helpers
    // ----------------------------------------------------------------

    /**
     * Build a PushNotifier appropriate for the current environment.
     *
     * <p>Environment variables consulted:
     * <ul>
     *   <li>{@code WEBHOOK_URL}    — full URL of the webhook endpoint (required for prod)</li>
     *   <li>{@code WEBHOOK_SECRET} — HMAC-SHA256 signing secret (optional but recommended)</li>
     * </ul>
     */
    private static PushNotifier buildNotifier() {
        String webhookUrl = System.getenv("WEBHOOK_URL");

        if (webhookUrl != null && !webhookUrl.isBlank()) {
            // Production: POST events to a real endpoint
            String secret = System.getenv("WEBHOOK_SECRET"); // may be null — signing is optional
            var notifier = WebhookPushNotifier.builder()
                .url(webhookUrl)
                .secret(secret)          // null → no signature header added
                .maxRetries(3)           // retry up to 3 times on 5xx with exponential back-off
                .timeout(Duration.ofSeconds(10))
                .build();

            System.out.println("[PersistenceLite] Push mode: WEBHOOK → " + webhookUrl
                + (secret != null ? " (signed)" : " (unsigned)"));
            return notifier;
        }

        // Development: log events at INFO level
        var notifier = new LogPushNotifier("com.a2alite.example.push", Level.INFO);
        System.out.println("[PersistenceLite] Push mode: LOG (set WEBHOOK_URL to switch to webhook)");
        return notifier;
    }
}
