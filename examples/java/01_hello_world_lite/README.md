# Hello Agent - A2A Lite (Java)

A simple greeting agent using the **real A2A Lite library** (`com.a2alite`).

## Prerequisites

- Java 17+
- The A2A Lite library built locally (see `packages/java/`)

## Building

```bash
# From the packages/java directory, publish to local Maven first
cd ../../../packages/java
./gradlew publishToMavenLocal

# Then build the example
cd examples/java/01_hello_world_lite
./gradlew build
```

## Running

```bash
./gradlew run
```

Or with Gradle wrapper:

```bash
gradle run
```

## API

### Agent Card
```bash
curl http://localhost:8787/.well-known/agent-card.json
```

### Send Message
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
        "parts": [{"text": "{\"skill\": \"greet\", \"params\": {\"name\": \"Alice\"}}"}]
      }
    }
  }'
```

## Key Features

- Uses real `com.a2alite.Agent` class
- Simple lambda-based skill registration
- Builder pattern for agent configuration
- Built-in A2A protocol handling
