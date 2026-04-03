import com.a2alite.Agent;
import com.a2alite.AgentNetwork;
import com.a2alite.SkillConfig;
import com.a2alite.streaming.StreamingHandler;

import java.util.Map;

/**
 * Client-side SSE streaming consumption.
 *
 * Two agents:
 *   - StoryAgent (port 8787) — streaming skill "tell_story"
 *   - DisplayAgent (port 8788) — skill "display_story" that streams from StoryAgent
 *
 * Run: ./gradlew run -PmainClass=ClientStreaming
 *
 * Test with:
 *   curl -X POST http://localhost:8788 \
 *     -H "Content-Type: application/json" \
 *     -d '{"jsonrpc":"2.0","method":"message/send","id":"1","params":{"message":{"role":"user","parts":[{"type":"text","text":"{\"skill\":\"display_story\",\"params\":{\"topic\":\"a brave robot\"}}"}],"messageId":"m1"}}}'
 */
class ClientStreaming {
    public static void main(String[] args) throws Exception {
        // 1. StoryAgent — streams a short story word-by-word
        var storyAgent = Agent.builder()
            .name("StoryAgent")
            .description("Tells short stories via streaming")
            .build();

        storyAgent.skill("tell_story", SkillConfig.of("Tell a short story", null, true), params -> {
            var topic = (String) params.getOrDefault("topic", "a curious cat");
            var words = ("Once upon a time there was " + topic +
                ". It went on an adventure. The end.").split(" ");

            return StreamingHandler.stream(sink -> {
                for (String word : words) {
                    sink.accept(word + " ");
                    try { Thread.sleep(200); }
                    catch (InterruptedException e) { Thread.currentThread().interrupt(); }
                }
            });
        });

        // Start StoryAgent on port 8787 in a background thread
        new Thread(() -> storyAgent.run(8787)).start();
        Thread.sleep(1000); // Wait for server to start

        // 2. DisplayAgent — consumes the stream from StoryAgent
        var network = new AgentNetwork();
        network.add("story", "http://localhost:8787");

        var displayAgent = Agent.builder()
            .name("DisplayAgent")
            .description("Displays a streamed story from StoryAgent")
            .network(network)
            .build();

        displayAgent.skill("display_story", params -> {
            var topic = (String) params.getOrDefault("topic", "a curious cat");

            System.out.println("\n--- Streaming story about: " + topic + " ---");

            StreamingHandler.StreamResult stream = displayAgent.streamDelegate(
                "story", "tell_story", Map.of("topic", topic));

            var sb = new StringBuilder();
            for (Object chunk : stream) {
                System.out.print(chunk);
                System.out.flush();
                sb.append(chunk);
            }

            System.out.println("\n--- End of story ---\n");
            return sb.toString();
        });

        displayAgent.run(8788);
    }
}
