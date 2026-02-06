import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

/**
 * Webhooks and push notifications.
 *
 * Run: ./gradlew run -PmainClass=Webhooks
 */
class Webhooks {
    private static final HttpClient httpClient = HttpClient.newHttpClient();
    private static final ObjectMapper mapper = new ObjectMapper();

    public static void main(String[] args) {
        var agent = Agent.builder().name("WebhookDemo").description("Shows webhooks").build();

        agent.onComplete((skill, result) -> System.out.printf("✅ Skill '%s' completed: %s%n", skill, result));

        agent.skill("long_task", SkillConfig.of("Task that takes time"), params -> {
            double duration = ((Number) params.getOrDefault("duration", 2.0)).doubleValue();
            String callbackUrl = (String) params.get("callback_url");
            System.out.printf("Starting task (%ss)...%n", duration);
            try { Thread.sleep((long) (duration * 1000)); }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            var result = Map.of("status", "completed", "duration", duration);
            if (callbackUrl != null) notifyWebhook(callbackUrl, result);
            return result;
        });

        agent.skill("process_with_progress", SkillConfig.of("Task with progress"), params -> {
            int items = ((Number) params.getOrDefault("items", 10)).intValue();
            String callbackUrl = (String) params.get("callback_url");
            for (int i = 0; i < items; i++) {
                try { Thread.sleep(500); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                if (callbackUrl != null) notifyWebhook(callbackUrl, Map.of("progress", (i+1.0)/items));
            }
            return Map.of("processed", items, "status", "done");
        });

        agent.run(8787);
    }

    private static void notifyWebhook(String url, Object payload) {
        try {
            var request = HttpRequest.newBuilder().uri(URI.create(url))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(payload))).build();
            httpClient.sendAsync(request, HttpResponse.BodyHandlers.discarding());
        } catch (Exception e) { System.err.println("Webhook failed: " + e.getMessage()); }
    }
}
