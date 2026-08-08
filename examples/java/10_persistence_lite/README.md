# Persistence Lite — A2A Lite (Java)

Shows how to plug a **TaskStore** and a **PushNotifier** into an A2A Lite agent without changing the agent's business logic.

## What it demonstrates

| Concept | Implementation |
|---|---|
| Task persistence | `InMemoryTaskStore` (swap for Redis/JDBC in prod) |
| Dev notifications | `LogPushNotifier` — events logged to console |
| Prod notifications | `WebhookPushNotifier` — events POSTed as signed JSON |
| Skills | `echo` (trivial) and `slowSum` (long-running) |

## Prerequisites

- Java 17+
- A2A Lite published to local Maven (see below)

## Building

```bash
# 1. Publish the library to local Maven
cd ../../../packages/java
./gradlew publishToMavenLocal

# 2. Build and run the example
cd examples/java/10_persistence_lite
./gradlew run
```

## Running

### Development mode (log notifications to console)

```bash
./gradlew run
```

### Production mode (send notifications to a webhook)

```bash
WEBHOOK_URL=https://example.com/hook \
WEBHOOK_SECRET=my-secret \
./gradlew run
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

Replace `InMemoryTaskStore` with any class implementing `com.a2alite.TaskStore`:

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
