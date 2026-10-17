# Persistence Lite — A2A Lite (Java)

Shows the legacy application-level **TaskStore** and completion-hook **PushNotifier** APIs.

This example's regular skills return Messages and do not create persisted protocol Tasks. Replacing `com.a2alite.TaskStore` alone does not persist SDK tasks, ownership, subscriptions or delivery queues. Use [example 11](../11_production_path_lite/) and `JdbcProtocolBackend` for that coherent boundary.

## What it demonstrates

| Concept | Implementation |
|---|---|
| Legacy application store | `InMemoryTaskStore`; configured here, not exercised by these regular skills |
| Dev notifications | `LogPushNotifier` — events logged to console |
| Operator-configured notifications | `WebhookPushNotifier` — JSON POSTs, optionally HMAC signed; no durable outbox |
| Skills | `echo` (trivial) and `slowSum` (long-running) |

## Prerequisites

- Java 17+
- Repository checkout; Gradle resolves the unpublished 1.2.0 library through the composite build

## Building

```bash
# From the repository root
cd examples/java
./gradlew :10_persistence_lite:build
```

## Running

Run these commands from `examples/java`.

### Development mode (log notifications to console)

```bash
./gradlew :10_persistence_lite:run
```

### Webhook mode (sends real requests to your configured endpoint)

```bash
WEBHOOK_URL=https://example.com/hook \
WEBHOOK_SECRET=my-secret \
./gradlew :10_persistence_lite:run
```

When `WEBHOOK_URL` is set the agent sends a JSON POST to that URL after every skill
completes. The `X-A2A-Signature: sha256=<hex>` header is added when `WEBHOOK_SECRET`
is also provided.

## API

### Agent card

```bash
curl http://localhost:8787/.well-known/agent-card.json
```

### echo skill

```bash
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m1",
        "parts": [{"text": "{\"skill\": \"echo\", \"params\": {\"message\": \"hello\"}}"}]
      }
    }
  }'
```

### slowSum skill

```bash
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "id": "2",
    "method": "SendMessage",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "m1",
        "parts": [{"text": "{\"skill\": \"slowSum\", \"params\": {\"n\": 5}}"}]
      }
    }
  }'
```

## Swapping the TaskStore

For application-level tasks, replace `InMemoryTaskStore` with a class implementing `com.a2alite.TaskStore`. This is separate from `.protocolBackend(...)`:

```java
TaskStore taskStore = new MyRedisTaskStore(redisClient);

var agent = Agent.builder()
    .name("PersistenceLiteAgent")
    .description("...")
    .taskStore(taskStore)
    .pushNotifier(notifier)
    .build();
```

## Swapping the PushNotifier

`PushNotifier` is a single-method interface:

```java
@FunctionalInterface
public interface PushNotifier {
    void notify(Map<String, Object> event);
}
```

Any lambda, method reference, or class implementing it can be passed to
`Agent.Builder.pushNotifier(...)`.
