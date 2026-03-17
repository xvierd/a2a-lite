# Hello World - Google A2A SDK (Java)

> **Official Google A2A SDK implementation in Java.**

This example demonstrates a simple greeting agent using Google's official A2A Java SDK with Javalin as the web framework.

---

## 📁 Files Overview

```
src/main/java/com/example/hello/
├── HelloAgent.java          # Main application
├── GreetingSkill.java       # Skill implementation
├── AgentCardProvider.java   # Agent card definition
└── MessageHandler.java      # A2A request handler
```

**Total: ~120 lines across 4 Java files**

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

### Test Agent Card

```bash
curl http://localhost:8787/.well-known/agent.json
```

### Test Greeting Skill

```bash
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{
          "type": "text",
          "text": "{\"skill\": \"greet\", \"params\": {\"name\": \"World\"}}"
        }],
        "messageId": "msg-1"
      }
    }
  }'
```

---

## 📖 Code Structure

### 1. HelloAgent.java

Main entry point that sets up the Javalin server and configures routes:

```java
Javalin app = Javalin.create()
    .get("/.well-known/agent.json", ctx -> {
        ctx.json(agentCard);
    })
    .post("/", ctx -> {
        // Handle A2A messages
    });
```

### 2. AgentCardProvider.java

Defines agent metadata and skills:

```java
AgentCard card = AgentCard.builder()
    .name("HelloAgent")
    .description("A simple greeting agent")
    .addSkill(Skill.builder()
        .name("greet")
        .inputSchema(schema)
        .build())
    .build();
```

### 3. GreetingSkill.java

Business logic implementation:

```java
public class GreetingSkill {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
```

### 4. MessageHandler.java

A2A protocol handling:

```java
public class MessageHandler {
    public JsonRpcResponse handle(JsonRpcRequest request) {
        // Parse message
        // Route to skill
        // Format response
    }
}
```

---

## 📊 Comparison

| Metric | Google SDK | A2A Lite |
|--------|------------|----------|
| Files | 4 | 1 |
| Lines | ~120 | ~25 |
| Boilerplate | High | Minimal |

See [A2A Lite version](../01_hello_world_lite/) for comparison.
