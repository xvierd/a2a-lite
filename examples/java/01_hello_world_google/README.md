# Hello World - A2A v1.0 From Scratch (Java)

> **A2A protocol v1.0 implemented by hand with Javalin + Jackson — no SDK.**

This example demonstrates a simple greeting agent that speaks the A2A v1.0
wire protocol directly (JSON-RPC over HTTP). For the official Java SDK
approach see `packages/java` (LiteAgentExecutor / Quarkus integration).

---

## 📁 Files Overview

```
src/main/java/com/example/hello/
├── HelloAgent.java          # Main application (server + agent card)
├── GreetingSkill.java       # Skill implementation
└── MessageHandler.java      # A2A request handler
```

**Total: ~300 lines across 3 Java files**

---

## 🚀 Quick Start

### Prerequisites

- Java 17 or higher
- Maven 3.8+

### Build and Run

```bash
cd java/01_hello_world_google
mvn clean package
mvn exec:java
```

The agent starts on `http://localhost:8787`

---

## 🧪 Testing

### Test Agent Card (A2A v1.0 discovery)

```bash
curl http://localhost:8787/.well-known/agent-card.json
```

### Test Greeting Skill

```bash
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{
    "jsonrpc": "2.0",
    "method": "SendMessage",
    "id": "1",
    "params": {
      "message": {
        "role": "ROLE_USER",
        "messageId": "msg-1",
        "parts": [{
          "text": "{\"skill\": \"greet\", \"params\": {\"name\": \"World\"}}"
        }]
      }
    }
  }'
```

Response (v1.0 shape):

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "message": {
      "messageId": "...",
      "role": "ROLE_AGENT",
      "parts": [{"text": "Hello, World!"}]
    }
  }
}
```

---

## 📖 Code Structure

### 1. HelloAgent.java

Main entry point that sets up the Javalin server and configures routes:

```java
Javalin app = Javalin.create();
app.get("/.well-known/agent-card.json", ctx -> {
    ctx.json(agentCard);
});
app.post("/", ctx -> {
    // Handle A2A SendMessage (sets A2A-Version: 1.0 response header)
});
```

The agent card follows the v1.0 shape: `supportedInterfaces` (with
`protocolBinding: "JSONRPC"` and `protocolVersion: "1.0"`), skills with
`id`/`name`/`description`/`tags`, `capabilities`, and
`defaultInputModes`/`defaultOutputModes`.

### 2. GreetingSkill.java

Business logic implementation:

```java
public class GreetingSkill {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

### 3. MessageHandler.java

A2A protocol handling:

```java
public class MessageHandler {
    public ObjectNode handle(ObjectNode request) {
        // Parse v1.0 message (parts carry {"text": ...} directly)
        // Route to skill
        // Format v1.0 response (role ROLE_AGENT, messageId, parts)
    }
}
```

---

## 📊 Comparison

| Metric | From scratch | A2A Lite |
|--------|--------------|----------|
| Files | 3 | 1 |
| Lines | ~300 | ~40 |
| Boilerplate | High | Minimal |

See [A2A Lite version](../01_hello_world_lite/) for comparison.
