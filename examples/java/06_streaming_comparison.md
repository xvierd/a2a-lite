# Java Streaming Comparison: Google A2A SDK vs A2A Lite

This document compares the streaming implementations between the official Google A2A Java SDK and the simplified A2A Lite approach.

## Quick Stats

| Metric | Google SDK | A2A Lite | Improvement |
|--------|------------|----------|-------------|
| **Lines of Code** | 908 | 182 | **80% reduction** |
| **Java Files** | 6 + 1 test | 1 + 1 test | **71% fewer files** |
| **Infrastructure Code** | 595 lines | 0 lines | **100% eliminated** |
| **Skill Logic** | 313 lines | 145 lines | **54% reduction** |
| **Setup Complexity** | High | Low | **Minimal boilerplate** |

## File Structure Comparison

### Google A2A SDK
```
06_streaming_google/
├── pom.xml                                    # Maven config
├── README.md                                  # Documentation
├── src/main/java/com/example/streaming/
│   ├── StreamingAgent.java                    # 412 lines (main)
│   ├── sse/
│   │   └── SseEventEmitter.java              # 183 lines (infrastructure)
│   └── skills/
│       ├── ChatSkill.java                    # 71 lines
│       ├── CountSkill.java                   # 50 lines
│       ├── StorySkill.java                   # 79 lines
│       └── ProgressSkill.java                # 88 lines
└── src/test/java/com/example/streaming/
    └── StreamingAgentTest.java               # 25 lines
```

### A2A Lite
```
06_streaming_lite/
├── pom.xml                                    # Maven config
├── README.md                                  # Documentation
├── src/main/java/com/example/streaming/
│   └── StreamingAgent.java                    # 145 lines (everything!)
└── src/test/java/com/example/streaming/
    └── StreamingAgentTest.java               # 37 lines
```

## Code Comparison

### Agent Setup

#### Google SDK (412 lines)
```java
public class StreamingAgent {
    private static final Map<String, SseEventEmitter> activeStreams = new ConcurrentHashMap<>();
    
    public static void main(String[] args) {
        // Create agent card manually
        ObjectNode agentCard = createAgentCard();
        
        // Setup Javalin server manually
        Javalin app = Javalin.create(config -> {
            config.showJavalinBanner = false;
        });
        
        // Define all routes manually
        app.get("/.well-known/agent.json", ctx -> { ... });
        app.get("/", ctx -> { ... });
        app.get("/stream/{taskId}", ctx -> { ... });
        app.post("/", ctx -> { ... });
        app.post("/stream", ctx -> { ... });
        
        // Create capabilities with streaming=true
        ObjectNode capabilities = mapper.createObjectNode();
        capabilities.put("streaming", true);
        
        app.start(PORT);
    }
    
    // Manual SSE connection handling
    private static void handleSseConnection(Context ctx) { ... }
    
    // Manual message handling
    private static void handleMessage(Context ctx) { ... }
    
    // Manual streaming request handling
    private static void handleStreamingRequest(Context ctx) { ... }
}
```

#### A2A Lite (145 lines total)
```java
public class StreamingAgent {
    public static void main(String[] args) {
        // Builder pattern - everything automatic
        var agent = Agent.builder()
            .name("StreamingAgent")
            .description("Streaming agent with A2A Lite")
            .version("1.0.0")
            .streaming(true)  // One line!
            .build();
        
        // Just define streaming skills
        agent.stream("chat", (params, stream) -> {
            // Streaming logic only
        });
        
        agent.run(8787);  // Server starts automatically
    }
}
```

### SSE Infrastructure

#### Google SDK (183 lines - manual)
```java
public class SseEventEmitter {
    private final Context ctx;
    private final PrintWriter writer;
    private final AtomicBoolean closed = new AtomicBoolean(false);
    
    public void sendEvent(String eventName, Object data) {
        // Manual event formatting
        String jsonData = mapper.writeValueAsString(data);
        writer.write("event: " + eventName + "\n");
        writer.write("data: " + jsonData + "\n\n");
        writer.flush();
    }
    
    public void sendToken(String token, int index, boolean isLast) { ... }
    public void sendProgress(int current, int total, String message) { ... }
    public void sendChunk(String chunk) { ... }
    // ... more manual implementations
}
```

#### A2A Lite (0 lines - built-in)
```java
// All SSE infrastructure is built into the framework!
// Just use the StreamContext methods:
stream.token(token, index, isLast);
stream.progress(current, total, message);
stream.chunk(data);
stream.status(status, message);
stream.event(name, data);
```

### Skill Definition

#### Google SDK (per skill)
```java
public class ChatSkill {
    public void stream(ObjectNode params, SseEventEmitter emitter) {
        try {
            String message = params.has("message") ? 
                params.get("message").asText() : "Hello";
            
            emitter.sendEvent("status", createStatus("processing", "..."));
            Thread.sleep(500);
            
            String response = generateResponse(message);
            String[] words = response.split(" ");
            
            for (int i = 0; i < words.length; i++) {
                emitter.sendToken(words[i], i, i == words.length - 1);
                Thread.sleep(100);
            }
            
            emitter.sendEvent("status", createStatus("completed", "..."));
            
        } catch (Exception e) {
            emitter.sendError("Error: " + e.getMessage());
        }
    }
}
```

#### A2A Lite (per skill)
```java
agent.stream("chat", (params, stream) -> {
    String message = params.has("message") ? 
        params.get("message").asText() : "Hello";
    
    stream.status("processing", "...");
    Thread.sleep(500);
    
    for (String word : generateResponse(message).split(" ")) {
        stream.token(word, index++, isLast);
        Thread.sleep(100);
    }
    
    stream.status("completed", "...");
});
```

## Feature Comparison

| Feature | Google SDK | A2A Lite |
|---------|------------|----------|
| Agent Card Generation | Manual | Automatic |
| SSE Infrastructure | Hand-coded | Built-in |
| Event Formatting | Manual | Automatic |
| Client Tracking | Manual map | Framework-managed |
| Connection Cleanup | Manual | Automatic |
| JSON-RPC Handling | Manual | Automatic |
| Error Handling | Manual per skill | Framework-level |
| Progress Events | Custom implementation | `stream.progress()` |
| Token Events | Custom implementation | `stream.token()` |
| Status Events | Custom implementation | `stream.status()` |
| Custom Events | Manual formatting | `stream.event()` |

## When to Use Each

### Use Google A2A SDK When:
- You need full control over every aspect
- Custom SSE event formats required
- Integration with existing infrastructure
- Learning the A2A protocol internals

### Use A2A Lite When:
- Rapid development is priority
- Standard SSE patterns are sufficient
- Reducing boilerplate is important
- Multiple streaming skills needed

## Testing

Both implementations provide the same endpoints:

```bash
# Check agent capabilities
curl http://localhost:8787/.well-known/agent.json

# Google SDK: Two-step streaming
curl -X POST http://localhost:8787/stream -d '{...}'  # Get stream URL
curl -N http://localhost:8787/stream/{taskId}         # Connect to SSE

# A2A Lite: Direct streaming
curl -N "http://localhost:8787/stream?skill=chat&message=Hello"
```

## Conclusion

**A2A Lite reduces streaming implementation from 908 to 182 lines (80% reduction)** while providing the same functionality:

- ✅ Same SSE protocol compliance
- ✅ Same streaming capabilities
- ✅ Same event types (token, progress, status, chunk)
- ✅ Same agent card with streaming=true
- ✅ Same client experience
- ⚡ 80% less code to maintain
- ⚡ 71% fewer files
- ⚡ Zero infrastructure code
