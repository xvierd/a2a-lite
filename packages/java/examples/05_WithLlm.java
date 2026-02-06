import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import java.util.Map;

/**
 * Agent that uses an LLM for intelligent responses.
 *
 * Run: export OPENAI_API_KEY=your-key && ./gradlew run -PmainClass=WithLlm
 */
class WithLlm {
    private static final HttpClient httpClient = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(30)).build();
    private static final ObjectMapper mapper = new ObjectMapper();
    private static final String apiKey = System.getenv("OPENAI_API_KEY");
    private static final String model = System.getenv().getOrDefault("OPENAI_MODEL", "gpt-4o-mini");

    private static Map<String, Object> chat(String message) {
        if (apiKey == null) return Map.of("error", "Set OPENAI_API_KEY env var");
        try {
            var body = mapper.writeValueAsString(Map.of("model", model, "messages",
                List.of(Map.of("role", "user", "content", message)), "max_tokens", 500));
            var request = HttpRequest.newBuilder()
                .uri(URI.create("https://api.openai.com/v1/chat/completions"))
                .header("Content-Type", "application/json")
                .header("Authorization", "Bearer " + apiKey)
                .POST(HttpRequest.BodyPublishers.ofString(body)).build();
            var response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            JsonNode json = mapper.readTree(response.body());
            return Map.of("response", json.get("choices").get(0).get("message").get("content").asText());
        } catch (Exception e) { return Map.of("error", e.getMessage()); }
    }

    public static void main(String[] args) {
        var agent = Agent.builder().name("SmartAssistant").description("AI-powered assistant").build();
        agent.skill("chat", SkillConfig.of("Chat with AI"), params -> chat((String) params.get("message")));
        agent.skill("summarize", SkillConfig.of("Summarize text"), params ->
            chat("Summarize in 100 words: " + params.get("text")));
        if (apiKey == null) System.out.println("WARNING: Set OPENAI_API_KEY for LLM features");
        agent.run(8787);
    }
}
