import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import java.util.List;
import java.util.Map;

/**
 * Human-in-the-loop (agent asks user questions).
 *
 * Run: ./gradlew run -PmainClass=HumanInTheLoop
 */
class HumanInTheLoop {
    public static void main(String[] args) {
        var agent = Agent.builder().name("Wizard").description("Interactive wizard").build();

        agent.skill("setup_wizard", SkillConfig.of("Multi-step wizard"), params -> {
            String name = (String) params.get("name");
            String role = (String) params.get("role");
            Boolean confirmed = (Boolean) params.get("confirmed");

            if (name == null) return Map.of("status", "input_required", "question", "What's your name?", "field", "name");
            if (role == null) return Map.of("status", "input_required", "question", "What's your role?", "field", "role",
                "options", List.of("Developer", "Designer", "Manager", "Other"));
            if (confirmed == null) return Map.of("status", "input_required",
                "question", "Create profile for " + name + " (" + role + ")?", "field", "confirmed", "type", "confirm");
            return confirmed ? Map.of("status", "created", "name", name, "role", role) : Map.of("status", "cancelled");
        });

        agent.skill("book_flight", SkillConfig.of("Book a flight"), params -> {
            String destination = (String) params.get("destination");
            String date = (String) params.get("date");
            String travelClass = (String) params.get("travel_class");
            Boolean confirmed = (Boolean) params.get("confirmed");

            if (date == null) return Map.of("status", "input_required", "question", "Travel date? (YYYY-MM-DD)", "field", "date");
            if (travelClass == null) return Map.of("status", "input_required", "question", "Which class?", "field", "travel_class",
                "options", List.of("Economy", "Business", "First"));
            if (confirmed == null) return Map.of("status", "input_required",
                "question", "Book " + travelClass + " to " + destination + " on " + date + "?", "field", "confirmed", "type", "confirm");
            return confirmed ? Map.of("status", "booked", "destination", destination, "date", date, "class", travelClass, "confirmation", "ABC123")
                : Map.of("status", "cancelled");
        });

        agent.run(8787);
    }
}
