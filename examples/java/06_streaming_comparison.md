# Java streaming: manual protocol and A2A Lite

The manual `06_streaming_google` example implements A2A v1.0 SSE using Javalin 7.2.3 and Jackson. It does not use the official A2A Java SDK. The `06_streaming_lite` example currently returns complete `chat`, `count` and `progress` results; it is a regular-skill API demonstration, not equivalent incremental streaming.

A2A Lite 1.2.0 itself supports real standalone SSE through SDK 1.4.0.Final. The runnable [production path example](11_production_path_lite/) demonstrates that implementation. Java 1.2.0 is verified in the checkout but not published to Maven Central; the examples use the local composite build.

## Run real streaming

From the repository root, start the Lite server:

```bash
cd examples/java
./gradlew :11_production_path_lite:run --args=learning
```

In a second terminal, also from `examples/java`, run the client:

```bash
./gradlew :11_production_path_lite:run --args=client
```

The client demonstrates Message, Task and streaming calls; the stream prints `one`, `two`, `three` in order. Alternatively, call the streaming skill directly:

```bash
curl -N http://127.0.0.1:8787/ \
  -H 'Content-Type: application/json' \
  -H 'A2A-Version: 1.0' \
  -d '{"jsonrpc":"2.0","id":"stream-1","method":"SendStreamingMessage","params":{"message":{"role":"ROLE_USER","messageId":"m1","parts":[{"text":"{\"skill\":\"stream\",\"params\":{}}"}]}}}'
```

For the manual implementation, stop the Lite server (both use port 8787), then follow [06_streaming_google](06_streaming_google/README.md).

## Implementation boundary

| Concern | Manual example | A2A Lite standalone |
|---------|----------------|---------------------|
| Routing and agent card | Application code | Library adapter |
| Initial Task and status/artifact events | Hand-built JSON | SDK handler and emitter |
| Streaming skill output | Custom `StreamEmitter` | `StreamingHandler.StreamResult` |
| Task ownership, cancellation and limits | Teaching subset | Runtime/backend contracts |
| Durable subscriptions | Not provided | Explicit JDBC backend, committed snapshot updates |

Javalin 7 registers routes inside its creation callback:

```java
Javalin app = Javalin.create(config -> {
    config.startup.showJavalinBanner = false;
    config.routes.get("/.well-known/agent-card.json", ctx -> ctx.json(agentCard));
    config.routes.post("/", ctx -> handleRequest(ctx));
});
app.start(8787);
```

Lite skill registration:

```java
import com.a2alite.SkillConfig;
import com.a2alite.streaming.StreamingHandler;
import java.util.List;

agent.skill("stream", SkillConfig.withStreaming(), params ->
    StreamingHandler.fromIterator(List.of("one", "two", "three").iterator()));
```

The response starts with `result.task`, followed by `result.statusUpdate` and `result.artifactUpdate` events. Task state determines success/failure; a disconnected stream alone does not prove completion. Durable cross-replica subscriptions emit committed status/artifact replacements rather than preserving the original chunk boundaries. See the [Java runtime guide](../../packages/java/README.md#managed-and-durable-operation) for admission, deadlines and cooperative cancellation.
