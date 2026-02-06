import com.a2alite.Agent;
import com.a2alite.SkillConfig;
import java.util.*;

/**
 * Reporter Agent - Part of multi-agent example.
 *
 * Run: ./gradlew run -PmainClass=multi_agent.ReporterAgent
 */
class ReporterAgent {
    public static void main(String[] args) {
        var agent = Agent.builder().name("ReporterAgent").description("Generates reports").build();

        agent.skill("generate_summary", SkillConfig.of("Generate summary report", List.of("reporting")), params -> {
            @SuppressWarnings("unchecked")
            Map<String, Object> data = (Map<String, Object>) params.get("data");
            String format = (String) params.getOrDefault("format", "text");
            StringBuilder sb = new StringBuilder();
            if ("markdown".equals(format)) {
                sb.append("# Summary Report\n\n");
                data.forEach((k, v) -> sb.append("- **").append(k).append("**: ").append(v).append("\n"));
            } else {
                sb.append("Summary Report\n").append("=".repeat(40)).append("\n");
                data.forEach((k, v) -> sb.append(k).append(": ").append(v).append("\n"));
            }
            return Map.of("report", sb.toString(), "format", format);
        });

        agent.skill("format_table", SkillConfig.of("Format as table", List.of("reporting")), params -> {
            @SuppressWarnings("unchecked")
            List<String> headers = (List<String>) params.get("headers");
            @SuppressWarnings("unchecked")
            List<List<Object>> rows = (List<List<Object>>) params.get("rows");
            int[] widths = new int[headers.size()];
            for (int i = 0; i < headers.size(); i++) {
                final int idx = i;
                int maxData = rows.stream().mapToInt(r -> String.valueOf(r.get(idx)).length()).max().orElse(0);
                widths[i] = Math.max(headers.get(i).length(), maxData);
            }
            StringBuilder sb = new StringBuilder();
            String sep = "+" + Arrays.stream(widths).mapToObj(w -> "-".repeat(w + 2)).reduce((a,b)->a+"+"+b).orElse("") + "+\n";
            sb.append(sep);
            for (int i = 0; i < headers.size(); i++) sb.append("| ").append(String.format("%-" + widths[i] + "s", headers.get(i))).append(" ");
            sb.append("|\n").append(sep);
            for (var row : rows) {
                for (int i = 0; i < row.size(); i++) sb.append("| ").append(String.format("%-" + widths[i] + "s", row.get(i))).append(" ");
                sb.append("|\n");
            }
            sb.append(sep);
            return Map.of("table", sb.toString());
        });

        agent.run(8789);
    }
}
