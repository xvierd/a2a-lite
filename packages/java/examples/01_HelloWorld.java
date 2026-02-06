import com.a2alite.Agent;
import com.a2alite.SkillConfig;

/**
 * Hello World - The simplest A2A agent.
 *
 * Run: ./gradlew run -PmainClass=HelloWorld
 */
class HelloWorld {
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("HelloBot")
            .description("A friendly greeting bot")
            .build();

        agent.skill("greet",
            SkillConfig.of("Greet someone by name"),
            params -> "Hello, " + params.get("name") + "!"
        );

        agent.run(8787);
    }
}
