# Java Examples: A2A v1.0 From Scratch vs A2A Lite

This directory contains side-by-side examples comparing a **hand-rolled A2A v1.0 protocol implementation** (Javalin + Jackson, no SDK) with the **A2A Lite** library approach. The examples use the **A2A protocol v1.0** wire format (`SendMessage`, `/.well-known/agent-card.json`, `A2A-Version: 1.0` header). Streaming examples additionally demonstrate `SendStreamingMessage`. The manual implementations cover a teaching subset, not the complete SDK lifecycle/security/runtime.

> **Note:** the `*_google` examples do **not** use the official A2A Java SDK — they implement the protocol from scratch to show the boilerplate cost. For the official SDK (`org.a2aproject.sdk`) see the [Java package guide](../../packages/java/README.md) (LiteAgentExecutor / Quarkus integration).

## Overview

| Approach | Build Tool | Library | Description |
|----------|-----------|---------|-------------|
| `*_google` | Maven | none (Javalin + Jackson) | A2A v1.0 protocol implemented from scratch |
| `*_lite` | Gradle | `io.github.xvierd:a2a-lite:1.2.0` | Simplified A2A Lite library (real library from packages/java/) |

**Java 1.2.0 is built and verified locally but is not published to Maven Central.** These Gradle examples resolve it from `packages/java` through the included composite build, without publishing or signing. The current stack is SDK `1.4.0.Final`, Javalin `7.2.3`, Jetty `12.1.14` and Jackson `2.22.3`.

## Showcase: Battleship (Python demo — same A2A v1.0 wire)

Playable multi-agent demo with web UI (implemented in Python with a2a-lite):

```bash
# from repo root
cd examples/python/11_battleship_lite
pip install -e ../../../packages/python
python agent.py    # http://localhost:8790/
# python arena.py  # http://localhost:8793/?mode=arena
```

→ [../python/11_battleship_lite/README.md](../python/11_battleship_lite/README.md)

## Available Examples

| # | Example | What to expect |
|---|---------|----------------|
| 01 | [Hello World](01_hello_world_lite/) | Message round trip; [manual counterpart](01_hello_world_google/) |
| 02 | [Calculator](02_calculator_lite/) | Multiple regular skills; [manual counterpart](02_calculator_google/) |
| 03 | [File Handling](03_file_handling_lite/) | Text/file operations; [manual counterpart](03_file_handling_google/) |
| 05 | [Authentication](05_auth_lite/) | API key setup; [manual demo credentials/RBAC](05_auth_google/) |
| 06 | [Streaming comparison](06_streaming_comparison.md) | Lite demo returns complete results; [manual example](06_streaming_google/) streams SSE |
| 08 | [LLM simulation](08_llm_integration_lite/) | Local keyword tools; [manual counterpart](08_llm_integration_google/) makes provider calls |
| 09 | [Human-in-the-Loop](09_human_in_loop_lite/) | Application-level confirmation IDs in a local map |
| 10 | [Legacy persistence hooks](10_persistence_lite/) | Application TaskStore and completion notifier; not durable protocol state |
| 11 | [Learning → durable service](11_production_path_lite/) | Real Task IDs, SSE, stable identity, PostgreSQL and checkpoint recovery |

## Quick Comparison

### From scratch (verbose, no SDK)

```java
// Manual HTTP handling, manual agent card, manual JSON-RPC
public class HelloAgent {
    public static void main(String[] args) {
        ObjectNode agentCard = createAgentCard();  // v1.0 card by hand

        Javalin app = Javalin.create(config -> {
            config.routes.get("/.well-known/agent-card.json", ctx -> ctx.json(agentCard));
            config.routes.post("/", ctx -> {
                // Validate jsonrpc, dispatch SendMessage, set A2A-Version header,
                // parse parts, route to skill, format v1.0 response — all manual
            });
        });
        app.start(8787);
    }
}
```

### A2A Lite (Concise)

```java
import com.a2alite.Agent;
import com.a2alite.SkillConfig;

public class HelloAgent {
    public static void main(String[] args) {
        var agent = Agent.builder()
            .name("HelloAgent")
            .description("A simple greeting agent")
            .build();
        
        agent.skill("greet", SkillConfig.of("Greet someone"), params -> {
            String name = (String) params.getOrDefault("name", "World");
            return Map.of("message", "Hello, " + name + "!");
        });
        
        agent.run(8787);  // Auto-starts server
    }
}
```

## Building and Running

### Prerequisites

1. Java 17+
2. Maven 3.8+ (for the `*_google` examples)
3. Gradle wrapper (included) for the `*_lite` examples — the A2A Lite library
   is resolved automatically from the composite build at `../../packages/java`.

### Step 1: Run a Lite Example

#### A2A Lite Examples (Gradle)

```bash
cd examples/java
./gradlew :01_hello_world_lite:run
```

#### From-scratch Examples (Maven)

```bash
cd examples/java/01_hello_world_google
mvn compile exec:java
```

## Example Structure

### A2A Lite Examples

```
01_hello_world_lite/
├── build.gradle                    # Gradle build file
├── README.md                       # Example documentation
└── src/main/java/com/example/hello/
    └── HelloAgent.java             # Main agent (~40 lines)
```

### From-scratch Examples

```
01_hello_world_google/
├── pom.xml                         # Maven build file
├── README.md                       # Example documentation
└── src/main/java/com/example/hello/
    ├── HelloAgent.java             # Main application
    ├── GreetingSkill.java          # Skill implementation
    └── MessageHandler.java         # Message routing
```

## API Usage Examples (A2A v1.0 wire)

The Hello World examples accept this v1.0 Message request:

```bash
# Get Agent Card (v1.0 well-known path)
curl http://localhost:8787/.well-known/agent-card.json

# Call a skill (SendMessage + mandatory A2A-Version header)
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

## Key Differences

| Aspect | From scratch (`*_google`) | A2A Lite |
|--------|---------------|----------|
| **Build Tool** | Maven | Gradle |
| **Agent Setup** | Manual `main()` + Javalin | Builder pattern |
| **Skill Registration** | Multiple classes | Lambda functions |
| **HTTP Handling** | Manual (Javalin) | Built-in |
| **Authentication** | Multiple classes | `APIKeyAuth`, `BearerAuth` |
| **JSON Handling** | Jackson manual | Jackson built-in |
| **Agent Card** | Manual construction | Auto-generated (v1.0 shape) |
| **A2A Protocol** | Manual implementation | Built-in |

## A2A Lite Library API

### Creating an Agent

```java
var agent = Agent.builder()
    .name("MyAgent")
    .description("My agent description")
    .version("1.0.0")
    .url("http://localhost:8080")
    .build();
```

### Registering Skills

```java
import com.a2alite.streaming.StreamingHandler;
import java.util.List;

// Simple skill
agent.skill("hello", params -> "Hello!");

// Skill with config
agent.skill("greet", SkillConfig.of("Greet by name"), params -> {
    String name = (String) params.get("name");
    return Map.of("message", "Hello, " + name + "!");
});

// Streaming skill
agent.skill("stream", SkillConfig.withStreaming(), params -> {
    return StreamingHandler.fromIterator(List.of("one", "two", "three").iterator());
});
```

### Authentication

```java
// API Key auth
var apiKeyAuth = new APIKeyAuth(Set.of("secret-key-1", "secret-key-2"), "X-API-Key");

// Bearer auth
var bearerAuth = new BearerAuth(token -> validateToken(token) ? "user-id" : null);

// Apply to agent
var agent = Agent.builder()
    .name("SecureAgent")
    .description("API-key protected skills")
    .auth(apiKeyAuth)
    .build();
```

### Running the Agent

```java
agent.run();        // Default port 8787
agent.run(8080);    // Custom port
agent.run("0.0.0.0", 8080);  // Custom host and port
```

## When to Use Each Approach

### Use the from-scratch approach when:
- Learning the A2A v1.0 wire protocol internals
- Comparing manually assembled JSON-RPC messages with SDK-backed behavior
- Studying a small transport example before choosing a maintained SDK

For an SDK/Quarkus integration, see the [Java package guide](../../packages/java/README.md#quarkus-integration), including its separate authorization configuration. The manual samples are not production server templates.

### Use A2A Lite when:
- Rapid prototyping and development
- Simple agents with few skills
- Standard A2A patterns suffice
- Less boilerplate code is desired
- Educational purposes
- Quick demos and POCs

## Project Structure

```
a2a-lite/
├── packages/java/                  # A2A Lite library (local implementation, v1.2.0)
│   ├── src/main/java/com/a2alite/
│   │   ├── Agent.java              # Main agent class
│   │   ├── SkillHandler.java       # Skill functional interface
│   │   ├── SkillConfig.java        # Skill configuration
│   │   └── auth/                   # Authentication providers
│   │       ├── APIKeyAuth.java
│   │       ├── BearerAuth.java
│   │       └── NoAuth.java
│   └── build.gradle
│
└── examples/java/                  # Examples
    ├── 01_hello_world_lite/        # A2A Lite version (Gradle)
    ├── 01_hello_world_google/      # From-scratch version (Maven, no SDK)
    ├── 02_calculator_lite/
    ├── 02_calculator_google/
    └── ... (more examples)
```

## Building All Examples

### Build All Lite Examples

The composite build resolves the A2A Lite library directly from
`packages/java` — no `publishToMavenLocal` needed:

```bash
cd examples/java
./gradlew build
```

### Run Specific Example

```bash
cd examples/java
./gradlew :01_hello_world_lite:run
./gradlew :02_calculator_lite:run
./gradlew :05_auth_lite:run
./gradlew :10_persistence_lite:run
./gradlew :11_production_path_lite:run --args=learning
```

## Next step

Use [example 11](11_production_path_lite/) for the progressive production path and [OPERATIONS.md](../../OPERATIONS.md) for verified limits and deployment gates. The smaller examples isolate learning concepts; their local maps, simulated outputs and manual protocol implementations do not inherit durable storage or multi-user business-state authorization automatically.
