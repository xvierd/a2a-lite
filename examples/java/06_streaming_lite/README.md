# Streaming Agent - A2A Lite (Java)

Streaming demonstration using the **real A2A Lite library**.

## Note on Streaming

This particular example registers regular `chat`, `count` and `progress` skills that return complete results. Its agent card does not advertise streaming; the console message suggesting a separate SDK server is required is outdated.

A2A Lite 1.2.0 already supports real SSE in standalone mode. Register a streaming skill and return a `StreamingHandler.StreamResult`:

```java
agent.skill("stream", SkillConfig.withStreaming(), params ->
    StreamingHandler.fromIterator(List.of("one", "two", "three").iterator()));
```

Import `com.a2alite.streaming.StreamingHandler` and `java.util.List` for this snippet. The runnable [production path example](../11_production_path_lite/) includes this skill and a client that consumes its ordered chunks. The [manual streaming example](../06_streaming_google/) implements SSE itself and does not use the official SDK.

## Running

```bash
# From the repository root; resolves the local 1.2.0 library via composite build
cd examples/java
./gradlew :06_streaming_lite:run
```
