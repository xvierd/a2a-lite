import com.a2alite.Agent;
import com.a2alite.AgentRouter;

import java.util.Map;

/**
 * AgentRouter mounts multiple agents under a single HTTP server.
 *
 * GET / lists the mounted cards. Each card gives the complete JSON-RPC URL.
 * The root well-known card describes the first mount (weather in this example).
 *
 * GET  /weather/.well-known/agent-card.json
 * POST /weather
 * GET  /hotels/.well-known/agent-card.json
 * POST /hotels
 *
 * Run from packages/java:
 * ./gradlew writeInteropClasspath
 * java --class-path "$(cat build/interop-classpath.txt)" examples/18_Router.java
 */
class Router {
    public static void main(String[] args) {
        // --- Weather agent ---
        var weatherAgent = Agent.builder()
            .name("WeatherAgent")
            .description("Provides weather forecasts")
            .textEntrySkill("forecast")
            .build();

        weatherAgent.skill("forecast", params -> {
            String city = (String) params.getOrDefault("city", params.get("message"));
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
        System.out.println("  Directory:    http://localhost:8787/");
        System.out.println("  Weather:      http://localhost:8787/weather");
        System.out.println("  Hotels:       http://localhost:8787/hotels");

        router.run(8787);
    }
}
