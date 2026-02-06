import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import java.util.List;
import java.util.Map;

/**
 * Task lifecycle and progress tracking.
 *
 * Run: ./gradlew run -PmainClass=TaskTracking
 */
class TaskTracking {
    public static void main(String[] args) {
        var agent = Agent.builder().name("TaskTracker").description("Shows task progress").build();

        agent.skill("long_process", SkillConfig.of("Long task with progress", null, true), params -> {
            int steps = ((Number) params.getOrDefault("steps", 5)).intValue();
            System.out.println("Starting process...");
            for (int i = 0; i < steps; i++) {
                try { Thread.sleep(500); } catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                System.out.printf("Progress: %.0f%% - Step %d/%d%n", (i+1.0)/steps*100, i+1, steps);
            }
            return Map.of("status", "completed", "steps_completed", steps);
        });

        agent.skill("batch_import", SkillConfig.of("Import with progress", null, true), params -> {
            @SuppressWarnings("unchecked")
            List<String> items = (List<String>) params.get("items");
            int total = items.size(), successful = 0, failed = 0;
            System.out.printf("Importing %d items...%n", total);
            for (int i = 0; i < total; i++) {
                try { Thread.sleep(100); successful++; }
                catch (InterruptedException e) { Thread.currentThread().interrupt(); failed++; }
                System.out.printf("Progress: %.0f%% - %d/%d (%d failed)%n", (i+1.0)/total*100, i+1, total, failed);
            }
            return Map.of("total", total, "successful", successful, "failed", failed);
        });

        agent.run(8787);
    }
}
