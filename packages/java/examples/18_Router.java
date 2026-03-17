import com.a2alite.Agent;
import com.a2alite.AgentRouter;

import java.util.Map;

/**
 * AgentRouter mounts multiple agents under a single HTTP server.
 *
 * Each agent gets its own path prefix, and a merged agent card is
 * served at /.well-known/agent.json combining all mounted agents.
 *
 * Endpoints after starting:
 *   GET  /.well-known/agent.json          — merged card (all skills)
 *   GET  /weather/.well-known/agent.json  — weather agent card
 *   POST /weather                          — call weather skills
 *   GET  /hotels/.well-known/agent.json   — hotels agent card
 *   POST /hotels                           — call hotel skills
 *
 * Run: ./gradlew run -PmainClass=Router
 */
class Router {
    public static void main(String[] args) {
        // --- Weather agent ---
        var weatherAgent = Agent.builder()
            .name("WeatherAgent")
            .description("Provides weather forecasts")
            .build();

        weatherAgent.skill("forecast", params -> {
            String city = (String) params.get("city");
            return Map.of(
                "city", city,
                "temperature", "22C",
                "condition", "Sunny"
            );
        });

        weatherAgent.skill("alerts", params -> {
            String city = (String) params.get("city");
            return Map.of("city", city, "alerts", java.util.List.of());
        });

        // --- Hotels agent ---
        var hotelAgent = Agent.builder()
            .name("HotelAgent")
            .description("Searches for hotels")
            .build();

        hotelAgent.skill("search", params -> {
            String city = (String) params.get("city");
            return Map.of(
                "city", city,
                "hotels", java.util.List.of(
                    Map.of("name", "Grand Hotel", "price", "$200/night"),
                    Map.of("name", "Budget Inn", "price", "$85/night")
                )
            );
        });

        hotelAgent.skill("book", params -> Map.of(
            "confirmation", "BK-" + System.currentTimeMillis(),
            "hotel", params.get("hotel"),
            "status", "confirmed"
        ));

        // --- Router ---
        var router = new AgentRouter();
        router.mount("/weather", weatherAgent);
        router.mount("/hotels", hotelAgent);

        System.out.println("Endpoints:");
        System.out.println("  Merged card:  http://localhost:8787/.well-known/agent.json");
        System.out.println("  Weather:      http://localhost:8787/weather");
        System.out.println("  Hotels:       http://localhost:8787/hotels");

        router.run(8787);
    }
}
