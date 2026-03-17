# Java Examples: Google A2A SDK vs A2A Lite

This directory contains side-by-side examples comparing the **Google A2A SDK** approach with the **A2A Lite** library approach.

## Overview

| Approach | Build Tool | Library | Description |
|----------|-----------|---------|-------------|
| `*_google` | Maven | `io.github.a2asdk:a2a-java-sdk-server-common` | Official Google A2A SDK |
| `*_lite` | Gradle | `com.a2alite:a2a-lite` | Simplified A2A Lite library (real library from packages/java/) |

## Available Examples

| # | Example | Google SDK | A2A Lite | Lines Reduction |
|---|---------|-----------|----------|-----------------|
| 01 | Hello World | ~170 lines | ~40 lines | 76% |
| 02 | Calculator | ~180 lines | ~50 lines | 72% |
| 03 | File Handling | ~350 lines | ~80 lines | 77% |
| 05 | Authentication | ~963 lines | ~80 lines | 92% |
| 06 | Streaming | ~400 lines | ~60 lines | 85% |
| 08 | LLM Integration | ~765 lines | ~200 lines | 74% |
| 09 | Human-in-the-Loop | ~400 lines | ~150 lines | 63% |

## Quick Comparison

### Google A2A SDK (Verbose)

```java
// Multiple classes, explicit HTTP handling
@ApplicationScoped
public class HelloAgent {
    @Inject AgentExecutor executor;
    
    @Produces
    public AgentCard agentCard() {
        return new AgentCard.Builder()
            .name("HelloAgent")
            .capabilities(new AgentCapabilities.Builder()
                .streaming(false)
                .build())
            .skills(List.of(new AgentSkill.Builder()
                .id("greet")
                .name("Greet")
                .build()))
            .build();
    }
    
    // Manual message handling
    // Manual skill routing
    // Manual response formatting
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
2. The A2A Lite library published to local Maven repository

### Step 1: Build the A2A Lite Library

```bash
cd /path/to/a2a-lite/packages/java
./gradlew publishToMavenLocal
```

### Step 2: Run an Example

#### A2A Lite Examples (Gradle)

```bash
cd examples/java/01_hello_world_lite
./gradlew run
```

#### Google SDK Examples (Maven)

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

### Google SDK Examples

```
01_hello_world_google/
├── pom.xml                         # Maven build file
├── README.md                       # Example documentation
└── src/main/java/com/example/hello/
    ├── HelloAgent.java             # Main application
    ├── GreetingSkill.java          # Skill implementation
    └── MessageHandler.java         # Message routing
```

## API Usage Examples

### Test A2A Lite Agent

```bash
# Get Agent Card
curl http://localhost:8787/.well-known/agent.json

# Call a skill
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "1",
    "method": "message/send",
    "params": {
      "message": {
        "parts": [{"type": "text", "text": "{\"skill\": \"greet\", \"params\": {\"name\": \"Alice\"}}"}]
      }
    }
  }'
```

### Test Google SDK Agent

```bash
# Get Agent Card
curl http://localhost:8080/.well-known/agent.json

# Call a skill (endpoint varies by implementation)
curl -X POST http://localhost:8080/skills/greet \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice"}'
```

## Key Differences

| Aspect | Google A2A SDK | A2A Lite |
|--------|---------------|----------|
| **Build Tool** | Maven | Gradle |
| **Agent Setup** | Class-based, annotations | Builder pattern |
| **Skill Registration** | Multiple classes | Lambda functions |
| **HTTP Handling** | Manual (Javalin/Quarkus) | Built-in (Javalin via reflection) |
| **Authentication** | Multiple classes | `APIKeyAuth`, `BearerAuth` |
| **JSON Handling** | Jackson manual | Jackson built-in |
| **Agent Card** | Manual construction | Auto-generated |
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

### Use Google A2A SDK when:
- Maximum control over every detail is needed
- Integration with existing Quarkus/Spring infrastructure
- Custom A2A protocol extensions are required
- Full streaming SSE implementation needed
- Enterprise-grade production deployments

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
├── packages/java/                  # A2A Lite library (real implementation)
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
    ├── 01_hello_world_google/      # Google SDK version (Maven)
    ├── 02_calculator_lite/
    ├── 02_calculator_google/
    └── ... (more examples)
```

## Building All Examples

### Build A2A Lite Library

```bash
cd packages/java
./gradlew publishToMavenLocal
```

### Build All Lite Examples

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
```

## Conclusion

A2A Lite provides a **70-90% reduction in application code** while using the **real A2A Lite library** from `packages/java/`. The builder pattern and lambda-based skill registration make the code more readable and maintainable.

The `*_lite` examples now properly import from `com.a2alite.*` and use the actual library implementation rather than stubs or manual Javalin code.
