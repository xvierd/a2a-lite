# Java Streaming Comparison: A2A v1.0 From Scratch vs A2A Lite

This document compares the streaming implementations between a hand-rolled
A2A v1.0 protocol server (Javalin + Jackson, no SDK) and the simplified
A2A Lite approach. Both speak the **A2A protocol v1.0** wire format.

## Quick Stats

| Metric | From scratch | A2A Lite | Improvement |
|--------|------------|----------|-------------|
| **Lines of Code** | 826 | 97 | **88% reduction** |
| **Java Files** | 8 + 1 test | 1 | **89% fewer files** |
| **Infrastructure Code** | ~595 lines | 0 lines | **100% eliminated** |
| **Skill Logic** | ~230 lines | 97 lines | **58% reduction** |
| **Setup Complexity** | High | Low | **Minimal boilerplate** |

## File Structure Comparison

### From scratch (`06_streaming_google`, Maven, no SDK)
```
06_streaming_google/
├── pom.xml                                    # Maven config
├── README.md                                  # Documentation
├── src/main/java/com/example/streaming/
│   ├── StreamingAgent.java                    # 331 lines (main)
│   ├── sse/
│   │   ├── SseEventEmitter.java              # 163 lines (SSE wire v1.0)
│   │   ├── StreamEmitter.java                # 44 lines (sink interface)
│   │   └── CollectingEmitter.java            # 57 lines (SendMessage buffer)
│   └── skills/
│       ├── ChatSkill.java                    # 60 lines
│       ├── CountSkill.java                   # 40 lines
│       ├── StorySkill.java                   # 65 lines
│       └── ProgressSkill.java                # 66 lines
└── src/test/java/com/example/streaming/
    └── StreamingAgentTest.java               # 25 lines
```

### A2A Lite (`06_streaming_lite`, Gradle)
```
06_streaming_lite/
├── build.gradle                               # Gradle build file
├── README.md                                  # Documentation
└── src/main/java/com/example/streaming/
    └── StreamingAgent.java                    # 97 lines (everything!)
```

## Code Comparison

### Agent Setup

#### From scratch (331 lines)
```java
public class StreamingAgent {
    public static void main(String[] args) {
        // Create v1.0 agent card manually (supportedInterfaces, ...)
        ObjectNode agentCard = createAgentCard();

        // Setup Javalin server manually
        Javalin app = Javalin.create(config -> {
            config.showJavalinBanner = false;
        });

        // Define all routes manually
        app.get("/.well-known/agent-card.json", ctx -> { ... });
        app.post("/", ctx -> {
            // Dispatch SendMessage / SendStreamingMessage manually,
            // set A2A-Version: 1.0 header, validate JSON-RPC
        });

        app.start(PORT);
    }

    // Manual message handling
    private static void handleMessage(Context ctx) { ... }

    // Manual SSE-over-POST streaming
    private static void handleStreamingMessage(Context ctx) { ... }
}
```

#### A2A Lite (97 lines total)
```java
public class StreamingAgent {
    public static void main(String[] args) {
        // Builder pattern - everything automatic
        var agent = Agent.builder()
            .name("StreamingAgent")
            .description("Agent with simulated streaming capabilities")
            .version("1.0.0")
            .build();

        // Just define skills
        agent.skill("chat", SkillConfig.of("Chat with the agent"), params -> {
            // Skill logic only
        });

        agent.run(8792);  // Server starts automatically (v1.0 wire built-in)
    }
}
```

### SSE Infrastructure (v1.0 wire)

#### From scratch (264 lines - manual)
```java
public class SseEventEmitter implements StreamEmitter {
    private final Context ctx;
    private final PrintWriter writer;

    public void sendTask(ObjectNode task) {
        // First event: {"result":{"task":{...,"status":{"state":"TASK_STATE_SUBMITTED"}}}}
        writeSse(task);
    }

    public void sendStatus(String state, String message) {
        // {"result":{"statusUpdate":{"taskId","contextId","status":{
        //   "state":"TASK_STATE_WORKING","timestamp","message":{...}}}}}
        // NOTE: no "final" field — stream close marks terminality
    }

    public void sendText(String chunk, boolean last) {
        // {"result":{"artifactUpdate":{"taskId","artifact":{"artifactId",
        //   "parts":[{"text":...}]},"append":true,"lastChunk":false}}}
    }
    // ... more manual implementations
}
```

#### A2A Lite (0 lines - built-in)
```java
// All SSE/JSON-RPC infrastructure is built into the library.
// Streaming skills use SkillConfig.withStreaming():
agent.skill("stream_chat", SkillConfig.withStreaming(), params -> { ... });
// This enables streaming=true in the agent card capabilities and
// SendStreamingMessage support on the wire.
```

### Skill Definition

#### From scratch (per skill)
```java
public class ChatSkill {
    public void stream(ObjectNode params, StreamEmitter emitter) {
        try {
            String message = params.has("message") ?
                params.get("message").asText() : "Hello";

            emitter.sendStatus("TASK_STATE_WORKING", "Processing...");
            Thread.sleep(500);

            String[] words = generateResponse(message).split(" ");
            for (int i = 0; i < words.length; i++) {
                emitter.sendText(words[i] + " ", i == words.length - 1);
                Thread.sleep(100);
            }

            emitter.complete("Done");
        } catch (Exception e) {
            emitter.sendError("Error: " + e.getMessage());
        }
    }
}
```

#### A2A Lite (per skill)
```java
agent.skill("chat", SkillConfig.of("Chat with the agent"), params -> {
    String message = (String) params.getOrDefault("message", "Hello");
    return Map.of(
        "message", message,
        "response", generateResponse(message)
    );
});
```

## Feature Comparison

| Feature | From scratch | A2A Lite |
|---------|------------|----------|
| Agent Card Generation (v1.0 shape) | Manual | Automatic |
| SSE Infrastructure (`task`/`statusUpdate`/`artifactUpdate`) | Hand-coded | Built-in |
| Event Formatting (`TASK_STATE_*`, timestamps) | Manual | Automatic |
| Connection Cleanup | Manual | Automatic |
| JSON-RPC Handling (`SendMessage`/`SendStreamingMessage`) | Manual | Automatic |
| `A2A-Version: 1.0` header | Manual | Automatic |
| Error Handling | Manual per skill | Framework-level |
| Well-known `/.well-known/agent-card.json` | Manual route | Automatic |

## When to Use Each

### Use the from-scratch approach when:
- You need full control over every aspect
- Custom SSE event formats required
- Learning the A2A v1.0 protocol internals

### Use A2A Lite when:
- Rapid development is priority
- Standard A2A v1.0 patterns are sufficient
- Reducing boilerplate is important
- Multiple streaming skills needed

## Testing

Both implementations expose the same v1.0 endpoints:

```bash
# Check agent capabilities
curl http://localhost:8787/.well-known/agent-card.json

# Non-streaming call
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc":"2.0","id":"1","method":"SendMessage","params":{"message":
       {"role":"ROLE_USER","messageId":"m1",
        "parts":[{"text":"{\"skill\":\"chat\",\"params\":{\"message\":\"Hello\"}}"}]}}}'

# Streaming call (SSE directly on the POST response)
curl -N -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc":"2.0","id":"2","method":"SendStreamingMessage","params":{"message":
       {"role":"ROLE_USER","messageId":"m2",
        "parts":[{"text":"{\"skill\":\"count\",\"params\":{\"to\":3}}"}]}}}'
```

SSE events arrive as `data: {"result":{...}}` lines with keys `task`
(first event), `statusUpdate` (`TASK_STATE_WORKING` → `TASK_STATE_COMPLETED`)
and `artifactUpdate` — no `final` field; stream close marks terminality.

## Conclusion

**A2A Lite reduces the streaming implementation from 826 to 97 lines (88% reduction)**
while speaking the same A2A v1.0 wire protocol:

- ✅ Same SSE protocol compliance (v1.0 event keys, `TASK_STATE_*` states)
- ✅ Same streaming capabilities (`SendStreamingMessage`)
- ✅ Same agent card with streaming=true
- ✅ Same client experience
- ⚡ 88% less code to maintain
- ⚡ 89% fewer files
- ⚡ Zero infrastructure code
