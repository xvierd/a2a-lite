# Streaming Agent - A2A Lite (Java)

Streaming demonstration using the **real A2A Lite library**.

## Note on Streaming

True streaming in A2A requires the official A2A SDK with SSE (Server-Sent Events) support.

A2A Lite provides:
- `SkillConfig.withStreaming()` to mark skills as streaming-enabled
- Automatic streaming capability flags in the agent card

For full streaming implementation, use the A2A SDK integration mode (see 06_streaming_google).

## Running

```bash
./gradlew run
```
