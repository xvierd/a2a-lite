import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.*;
import java.util.concurrent.CompletableFuture;

/**
 * Agent demonstrating async operations.
 *
 * Run: ./gradlew run -PmainClass=AsyncAgent
 */
class AsyncAgent {
    private static final HttpClient httpClient = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(10)).build();

    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("AsyncDemo")
            .description("Demonstrates async operations")
            .build();

        agent.skill("delay", SkillConfig.of("Wait for specified seconds"), params -> {
            double seconds = ((Number) params.getOrDefault("seconds", 1.0)).doubleValue();
            try { Thread.sleep((long) (seconds * 1000)); }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            return Map.of("waited", seconds, "message", "Waited for " + seconds + " seconds");
        });

        agent.skill("fetch_data", SkillConfig.of("Fetch data from a URL"), params -> {
            String url = (String) params.get("url");
            try {
                var request = HttpRequest.newBuilder().uri(URI.create(url)).GET().build();
                var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
                return Map.of("status", response.statusCode(), "data", response.body());
            } catch (Exception e) {
                return Map.of("error", e.getMessage());
            }
        });

        agent.onStartup(() -> System.out.println("Agent starting..."));
        agent.onShutdown(() -> System.out.println("Agent stopping..."));

        agent.run(8787);
    }
}
