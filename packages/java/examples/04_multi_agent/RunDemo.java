import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.Map;

/**
 * Multi-Agent Demo - Orchestrates multiple agents.
 *
 * First start the agents:
 *   ./gradlew run -PmainClass=multi_agent.FinanceAgent
 *   ./gradlew run -PmainClass=multi_agent.ReporterAgent
 * Then run: ./gradlew run -PmainClass=multi_agent.RunDemo
 */
class RunDemo {
    private static final HttpClient http = HttpClient.newHttpClient();
    private static final ObjectMapper mapper = new ObjectMapper();

    public static void main(String[] args) throws Exception {
        System.out.println("🚀 Multi-Agent Demo\n");

        try {
            // Step 1: Get stock prices
            System.out.println("📊 Getting stock prices...");
            for (String symbol : new String[]{"AAPL", "GOOGL", "MSFT"}) {
                var result = callAgent("http://localhost:8788", "get_stock_price", Map.of("symbol", symbol));
                System.out.printf("   %s: $%s%n", symbol, result.get("price"));
            }

            // Step 2: Calculate portfolio
            System.out.println("\n💰 Calculating portfolio...");
            var portfolio = callAgent("http://localhost:8788", "get_portfolio_value",
                Map.of("holdings", Map.of("AAPL", 10, "GOOGL", 5, "MSFT", 8)));
            System.out.printf("   Total: $%.2f%n", ((Number) portfolio.get("total_value")).doubleValue());

            // Step 3: Generate report
            System.out.println("\n📝 Generating report...");
            var report = callAgent("http://localhost:8789", "generate_summary",
                Map.of("data", Map.of("portfolio_value", portfolio.get("total_value"), "stocks", 3), "format", "markdown"));
            System.out.println("\n" + report.get("report"));

            System.out.println("✅ Demo complete!");
        } catch (Exception e) {
            System.err.println("❌ Error: " + e.getMessage());
            System.out.println("\nStart agents first:\n  ./gradlew run -PmainClass=multi_agent.FinanceAgent\n  ./gradlew run -PmainClass=multi_agent.ReporterAgent");
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> callAgent(String url, String skill, Map<String, Object> params) throws Exception {
        var body = mapper.writeValueAsString(Map.of("jsonrpc", "2.0", "id", "1", "method", "message/send",
            "params", Map.of("message", Map.of("role", "user", "parts",
                new Object[]{Map.of("kind", "text", "text", mapper.writeValueAsString(Map.of("skill", skill, "params", params)))}))));
        var request = HttpRequest.newBuilder().uri(URI.create(url))
            .header("Content-Type", "application/json").POST(HttpRequest.BodyPublishers.ofString(body)).build();
        var response = http.send(request, HttpResponse.BodyHandlers.ofString());
        JsonNode json = mapper.readTree(response.body());
        String text = json.at("/result/parts/0/text").asText();
        return mapper.readValue(text, Map.class);
    }
}
