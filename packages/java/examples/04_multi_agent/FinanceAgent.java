import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import java.util.*;

/**
 * Finance Agent - Part of multi-agent example.
 *
 * Run: ./gradlew run -PmainClass=multi_agent.FinanceAgent
 */
class FinanceAgent {
    private static final Map<String, Double> stockPrices = Map.of(
        "AAPL", 178.50, "GOOGL", 141.25, "MSFT", 378.90, "AMZN", 178.25, "TSLA", 248.50
    );

    public static void main(String[] args) {
        var agent = Agent.builder().name("FinanceAgent").description("Financial data and analysis").build();

        agent.skill("get_stock_price", SkillConfig.of("Get stock price", List.of("finance")), params -> {
            String symbol = ((String) params.get("symbol")).toUpperCase();
            Double price = stockPrices.get(symbol);
            if (price == null) return Map.of("error", "Unknown symbol: " + symbol);
            return Map.of("symbol", symbol, "price", price, "currency", "USD");
        });

        agent.skill("get_portfolio_value", SkillConfig.of("Calculate portfolio value", List.of("finance")), params -> {
            @SuppressWarnings("unchecked")
            Map<String, Number> holdings = (Map<String, Number>) params.get("holdings");
            double total = 0;
            List<Map<String, Object>> details = new ArrayList<>();
            for (var entry : holdings.entrySet()) {
                String symbol = entry.getKey().toUpperCase();
                int shares = entry.getValue().intValue();
                double price = stockPrices.getOrDefault(symbol, 0.0);
                double value = price * shares;
                total += value;
                details.add(Map.of("symbol", symbol, "shares", shares, "price", price, "value", value));
            }
            return Map.of("total_value", total, "currency", "USD", "holdings", details);
        });

        agent.run(8788);
    }
}
