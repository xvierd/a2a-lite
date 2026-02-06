import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import java.util.Map;

/**
 * Calculator agent with multiple skills.
 *
 * Run: ./gradlew run -PmainClass=Calculator
 */
class Calculator {
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("Calculator")
            .description("Performs mathematical operations")
            .version("1.0.0")
            .build();

        agent.skill("add", SkillConfig.of("Add two numbers"), params -> {
            double a = ((Number) params.get("a")).doubleValue();
            double b = ((Number) params.get("b")).doubleValue();
            return a + b;
        });

        agent.skill("subtract", SkillConfig.of("Subtract b from a"), params -> {
            double a = ((Number) params.get("a")).doubleValue();
            double b = ((Number) params.get("b")).doubleValue();
            return a - b;
        });

        agent.skill("multiply", SkillConfig.of("Multiply two numbers"), params -> {
            double a = ((Number) params.get("a")).doubleValue();
            double b = ((Number) params.get("b")).doubleValue();
            return a * b;
        });

        agent.skill("divide", SkillConfig.of("Divide a by b"), params -> {
            double a = ((Number) params.get("a")).doubleValue();
            double b = ((Number) params.get("b")).doubleValue();
            if (b == 0) return Map.of("error", "Cannot divide by zero");
            return Map.of("result", a / b);
        });

        agent.onError(e -> Map.of(
            "error", e.getMessage(),
            "type", e.getClass().getSimpleName(),
            "hint", "Check your input parameters"
        ));

        agent.run(8787);
    }
}
