import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import java.util.Map;

/**
 * Using middleware for logging, timing, auth, etc.
 *
 * Run: ./gradlew run -PmainClass=Middleware
 */
class Middleware {
    public static void main(String[] args) {
        var agent = Agent.builder().name("MiddlewareDemo").description("Shows middleware").build();

        // Logging middleware
        agent.use((ctx, next) -> {
            System.out.printf("📥 Request: skill=%s, params=%s%n", ctx.skill(), ctx.params());
            long start = System.currentTimeMillis();
            Object result = next.call();
            System.out.printf("📤 Response: %dms%n", System.currentTimeMillis() - start);
            return result;
        });

        // Metadata middleware
        agent.use((ctx, next) -> {
            ctx.metadata().put("request_id", "req-" + System.currentTimeMillis());
            return next.call();
        });

        agent.skill("slow_operation", SkillConfig.of("Simulate slow operation"), params -> {
            double seconds = ((Number) params.getOrDefault("seconds", 1.0)).doubleValue();
            try { Thread.sleep((long) (seconds * 1000)); }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); }
            return Map.of("waited", seconds, "message", "Done!");
        });

        agent.skill("fast_operation", SkillConfig.of("Quick calculation"), params ->
            Map.of("result", ((Number) params.get("x")).intValue() * 2));

        agent.run(8787);
    }
}
