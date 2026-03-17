import com.a2alite.Agent;
import com.a2alite.AgentNetwork;

import java.util.Map;

/**
 * Multi-agent network with orchestration.
 *
 * Three agents collaborate via the AgentNetwork:
 *   - WeatherAgent   (port 8788) — provides weather forecasts
 *   - HotelAgent     (port 8789) — searches for hotels
 *   - Orchestrator   (port 8787) — delegates to both and combines results
 *
 * Run each agent in a separate terminal:
 *   Terminal 1: java 17_MultiAgentNetwork.java weather
 *   Terminal 2: java 17_MultiAgentNetwork.java hotels
 *   Terminal 3: java 17_MultiAgentNetwork.java orchestrator
 *
 * Or with Gradle:
 *   ./gradlew run -PmainClass=MultiAgentNetwork -Pargs=weather
 *   ./gradlew run -PmainClass=MultiAgentNetwork -Pargs=hotels
 *   ./gradlew run -PmainClass=MultiAgentNetwork -Pargs=orchestrator
 */
class MultiAgentNetwork {

    static Agent createWeatherAgent() {
        var agent = Agent.builder()
            .name("WeatherAgent")
            .description("Provides weather forecasts")
            .build();

        agent.skill("forecast", params -> {
            String city = (String) params.get("city");
            // Simulated weather data
            return Map.of(
                "city", city,
                "temperature", "22C",
                "condition", "Partly cloudy",
                "humidity", "65%"
            );
        });

        return agent;
    }

    static Agent createHotelAgent() {
        var agent = Agent.builder()
            .name("HotelAgent")
            .description("Searches for hotels")
            .build();

        agent.skill("search", params -> {
            String city = (String) params.get("city");
            // Simulated hotel data
            return Map.of(
                "city", city,
                "hotels", java.util.List.of(
                    Map.of("name", "Grand Hotel", "rating", 4.5, "price", "$200/night"),
                    Map.of("name", "Budget Inn", "rating", 3.8, "price", "$85/night"),
                    Map.of("name", "Luxury Suites", "rating", 4.9, "price", "$450/night")
                )
            );
        });

        return agent;
    }

    static Agent createOrchestratorAgent() {
        var network = new AgentNetwork();
        network.add("weather", "http://localhost:8788");
        network.add("hotels", "http://localhost:8789");

        var orchestrator = Agent.builder()
            .name("TravelPlanner")
            .description("Plans trips by coordinating weather and hotel agents")
            .network(network)
            .build();

        orchestrator.skill("plan_trip", params -> {
            String city = (String) params.get("city");

            Object weather = orchestrator.delegate("weather", "forecast", Map.of("city", city));
            Object hotels = orchestrator.delegate("hotels", "search", Map.of("city", city));

            return Map.of(
                "city", city,
                "weather", weather,
                "hotels", hotels
            );
        });

        return orchestrator;
    }

    public static void main(String[] args) {
        String role = args.length > 0 ? args[0] : "orchestrator";

        switch (role) {
            case "weather" -> {
                System.out.println("Starting WeatherAgent on port 8788...");
                createWeatherAgent().run(8788);
            }
            case "hotels" -> {
                System.out.println("Starting HotelAgent on port 8789...");
                createHotelAgent().run(8789);
            }
            default -> {
                System.out.println("Starting TravelPlanner orchestrator on port 8787...");
                System.out.println("Make sure WeatherAgent (8788) and HotelAgent (8789) are running.");
                createOrchestratorAgent().run(8787);
            }
        }
    }
}
