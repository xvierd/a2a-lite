# Java Examples: A2A v1.0 From Scratch vs A2A Lite

This directory contains side-by-side examples comparing a **hand-rolled A2A v1.0 protocol implementation** (Javalin + Jackson, no SDK) with the **A2A Lite** library approach. All examples speak the **A2A protocol v1.0** wire format (`SendMessage`/`SendStreamingMessage`, `/.well-known/agent-card.json`, `A2A-Version: 1.0` header).

> **Note:** the `*_google` examples do **not** use the official A2A Java SDK — they implement the protocol from scratch to show the boilerplate cost. For the official SDK (`org.a2aproject.sdk`) see `packages/java` (LiteAgentExecutor / Quarkus integration).

## Overview

| Approach | Build Tool | Library | Description |
|----------|-----------|---------|-------------|
| `*_google` | Maven | none (Javalin + Jackson) | A2A v1.0 protocol implemented from scratch |
| `*_lite` | Gradle | `io.github.xvierd:a2a-lite:1.0.0` | Simplified A2A Lite library (real library from packages/java/) |

## Available Examples

| # | Example | From scratch | A2A Lite | Lines Reduction |
|---|---------|-----------|----------|-----------------|
| 01 | Hello World | ~340 lines | ~50 lines | 85% |
| 02 | Calculator | ~330 lines | ~67 lines | 80% |
| 03 | File Handling | ~810 lines | ~180 lines | 78% |
| 05 | Authentication | ~1130 lines | ~68 lines | 94% |
| 06 | Streaming | ~825 lines | ~97 lines | 88% |
| 08 | LLM Integration | ~980 lines | ~204 lines | 79% |
| 09 | Human-in-the-Loop | — | ~230 lines | (lite only) |
| 10 | Persistence | — | ~150 lines | (lite only) |

## Quick Comparison

### From scratch (verbose, no SDK)

```java
// Manual HTTP handling, manual agent card, manual JSON-RPC
public class HelloAgent {
    public static void main(String[] args) {
        ObjectNode agentCard = createAgentCard();  // v1.0 card by hand

        Javalin app = Javalin.create();
        app.get("/.well-known/agent-card.json", ctx -> ctx.json(agentCard));
        app.post("/", ctx -> {
            // Validate jsonrpc, dispatch SendMessage, set A2A-Version header,
            // parse parts, route to skill, format v1.0 response — all manual
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
├── settings.gradle                 # Project settings
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

Both example families speak the same v1.0 wire protocol:

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
// Simple skill
agent.skill("hello", params -> "Hello!");

// Skill with config
agent.skill("greet", SkillConfig.of("Greet by name"), params -> {
    String name = (String) params.get("name");
    return Map.of("message", "Hello, " + name + "!");
});

// Streaming skill
agent.skill("stream", SkillConfig.withStreaming(), params -> {
    // Returns streaming response
    return "streaming data...";
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
- Maximum control over every HTTP/JSON detail is needed
- Custom A2A protocol extensions are required

(For production use of the official SDK — `org.a2aproject.sdk` with Quarkus —
see the integration in `packages/java`.)

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
├── packages/java/                  # A2A Lite library (real implementation, v1.0.0)
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
```

## Conclusion

A2A Lite provides a **~80-90% reduction in application code** while using the **real A2A Lite library** from `packages/java/`. The builder pattern and lambda-based skill registration make the code more readable and maintainable.

The `*_lite` examples import from `com.a2alite.*` and use the actual library implementation rather than stubs or manual Javalin code.
