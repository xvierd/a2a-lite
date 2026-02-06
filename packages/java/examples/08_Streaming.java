import com.a2alite.Agent;
import com.a2alite.SkillConfig;

/**
 * Streaming responses (like ChatGPT).
 *
 * Run: ./gradlew run -PmainClass=Streaming
 */
class Streaming {
    public static void main(String[] args) {
        var agent = Agent.builder().name("StreamingDemo").description("Shows streaming").build();

        agent.skill("count", SkillConfig.of("Count from 1 to n", null, true), params -> {
            int n = ((Number) params.getOrDefault("n", 5)).intValue();
            double delay = ((Number) params.getOrDefault("delay", 0.5)).doubleValue();
            StringBuilder result = new StringBuilder();
            for (int i = 1; i <= n; i++) {
                result.append("Count: ").append(i).append("\n");
                try { Thread.sleep((long) (delay * 1000)); }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            }
            return result.append("Done!").toString();
        });

        agent.skill("typewriter", SkillConfig.of("Type message slowly", null, true), params -> {
            String message = (String) params.get("message");
            StringBuilder result = new StringBuilder();
            for (char c : message.toCharArray()) {
                result.append(c);
                try { Thread.sleep(50); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            }
            return result.toString();
        });

        agent.run(8787);
    }
}
