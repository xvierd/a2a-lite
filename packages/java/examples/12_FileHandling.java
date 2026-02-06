import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.*;

/**
 * Multi-modal file handling.
 *
 * Run: ./gradlew run -PmainClass=FileHandling
 */
class FileHandling {
    public static void main(String[] args) {
        var agent = Agent.builder().name("FileProcessor").description("Processes files").build();

        agent.skill("summarize_doc", SkillConfig.of("Summarize a document"), params -> {
            @SuppressWarnings("unchecked")
            Map<String, Object> doc = (Map<String, Object>) params.get("document");
            String name = (String) doc.get("name");
            byte[] decoded = Base64.getDecoder().decode((String) doc.get("data"));
            String content = new String(decoded, StandardCharsets.UTF_8);
            String[] words = content.split("\\s+");
            String summary = String.join(" ", Arrays.copyOf(words, Math.min(50, words.length))) + "...";
            return "Summary of " + name + ": " + summary;
        });

        agent.skill("process_data", SkillConfig.of("Process JSON data"), params -> {
            @SuppressWarnings("unchecked")
            Map<String, Object> data = (Map<String, Object>) params.get("data");
            @SuppressWarnings("unchecked")
            List<Map<String, Object>> items = (List<Map<String, Object>>) data.getOrDefault("items", List.of());
            double total = items.stream().mapToDouble(i -> ((Number) i.getOrDefault("value", 0)).doubleValue()).sum();
            return Map.of("processed", items.size(), "total", total);
        });

        agent.skill("generate_report", SkillConfig.of("Generate a report"), params -> {
            String title = (String) params.get("title");
            return Map.of("name", "report.json", "parts", List.of(
                Map.of("kind", "text", "text", "# Report: " + title),
                Map.of("kind", "data", "data", Map.of("title", title, "generated", LocalDate.now().toString()))
            ));
        });

        agent.skill("analyze_image", SkillConfig.of("Analyze an image"), params -> {
            @SuppressWarnings("unchecked")
            Map<String, Object> image = (Map<String, Object>) params.get("image");
            String mimeType = (String) image.get("mimeType");
            if (!mimeType.startsWith("image/")) return Map.of("error", "Expected image, got " + mimeType);
            byte[] decoded = Base64.getDecoder().decode((String) image.get("data"));
            return Map.of("filename", image.get("name"), "mime_type", mimeType, "size_bytes", decoded.length);
        });

        agent.run(8787);
    }
}
