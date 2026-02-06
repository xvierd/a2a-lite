# A2A Lite — Java

[![GitHub](https://img.shields.io/badge/GitHub-a2a--lite-blue?logo=github)](https://github.com/xvierd/a2a-lite)

**Build A2A agents in 8 lines. Add features when you need them.**

Wraps the official [A2A Java SDK](https://github.com/a2aproject/a2a-java) with a simple, builder-based API. 100% protocol-compatible.

```java
var agent = Agent.builder()
    .name("Bot")
    .description("My bot")
    .build();

agent.skill("greet", params -> "Hello, " + params.get("name") + "!");

agent.run();
```

---

## Installation

### Gradle

```groovy
dependencies {
    implementation 'com.a2alite:a2a-lite:0.2.5'
    implementation 'io.javalin:javalin:5.6.3'
}
```

### Maven

```xml
<dependency>
    <groupId>com.a2alite</groupId>
    <artifactId>a2a-lite</artifactId>
    <version>0.2.5</version>
</dependency>

<dependency>
    <groupId>io.javalin</groupId>
    <artifactId>javalin</artifactId>
    <version>5.6.3</version>
</dependency>
```

**Requirements:** Java 17+

---

## Quick Start

### 1. Create an agent

```java
import com.a2alite.Agent;

var agent = Agent.builder()
    .name("Calculator")
    .description("Does math")
    .build();

agent.skill("add", params -> {
    int a = (int) params.get("a");
    int b = (int) params.get("b");
    return a + b;
});

agent.skill("multiply", params -> {
    int a = (int) params.get("a");
    int b = (int) params.get("b");
    return a * b;
});

agent.run(); // Listening on http://localhost:8787
```

### 2. Test it (no HTTP needed)

```java
import com.a2alite.testing.AgentTestClient;
import java.util.Map;

var client = new AgentTestClient(agent);
var result = client.call("add", Map.of("a", 2, "b", 3));
assertThat(result.getData()).isEqualTo(5);
```

---

## Features

### Skills

```java
// Simple skill
agent.skill("greet", params ->
    "Hello, " + params.get("name") + "!"
);

// With description and tags
agent.skill("greet",
    SkillConfig.of("Greet someone by name", List.of("greeting")),
    params -> "Hello, " + params.get("name") + "!"
);

// Streaming
agent.skill("stream",
    SkillConfig.withStreaming(),
    params -> "Streaming result"
);
```

### Middleware

Cross-cutting concerns without touching skill code:

```java
agent.use((ctx, next) -> {
    System.out.println("Calling: " + ctx.skill());
    Object result = next.call();
    System.out.println("Result: " + result);
    return result;
});
```

### Authentication

API keys are hashed in memory using SHA-256 — plaintext keys are never stored.

```java
import com.a2alite.auth.APIKeyAuth;
import com.a2alite.auth.BearerAuth;

// API Key
var agent = Agent.builder()
    .name("SecureBot")
    .description("A secure bot")
    .auth(new APIKeyAuth(Set.of("secret-key")))
    .build();

// Bearer token with custom validator
var agent2 = Agent.builder()
    .name("JWTBot")
    .description("JWT-protected bot")
    .auth(new BearerAuth(token -> valid(token) ? "user-id" : null))
    .build();
```

### Lifecycle Hooks

```java
agent.onStartup(() -> System.out.println("Agent starting"));
agent.onShutdown(() -> System.out.println("Agent stopping"));
agent.onComplete((skill, result) -> System.out.println("Completed: " + skill));
agent.onError(e -> Map.of("error", e.getMessage()));
```

---

## Testing

`AgentTestClient` lets you test without starting an HTTP server:

```java
import com.a2alite.testing.AgentTestClient;
import java.util.Map;

var client = new AgentTestClient(agent);

// Regular call
var result = client.call("greet", Map.of("name", "World"));
assertThat(result.getData()).isEqualTo("Hello, World!");

// Inspect the agent
List<String> skills = client.listSkills();
ObjectNode card = client.getAgentCard();
```

`AgentTestClient` returns a `TestResult` with `.getData()`, `.getText()`, and `.as(Class<T>)`.

---

## Agent Builder

```java
var agent = Agent.builder()
    .name("Bot")                       // Required
    .description("...")                // Required
    .version("1.0.0")                  // Optional, default "1.0.0"
    .url(null)                         // Optional, auto-detected
    .auth(new APIKeyAuth(...))         // Optional
    .build();
```

## Run Options

```java
agent.run();                           // Default port 8787
agent.run(9000);                       // Custom port
agent.run("localhost", 9000);          // Custom host and port
```

---

## Quarkus Integration

For Quarkus applications, use CDI producer classes to integrate with the framework:

```java
@ApplicationScoped
public class AgentCardProducer {
    @Inject
    Agent agent;

    @Produces
    @PublicAgentCard
    public AgentCard agentCard() {
        return agent.buildAgentCard("localhost", 8080);
    }
}

@ApplicationScoped
public class AgentExecutorProducer {
    @Inject
    Agent agent;

    @Produces
    public AgentExecutor agentExecutor() {
        return agent.getExecutor();
    }
}
```

---

## A2A Protocol Mapping

Everything maps directly to the underlying protocol — no magic, no lock-in.

| A2A Lite | A2A Protocol |
|----------|--------------|
| `agent.skill()` | Agent Skills |
| `SkillConfig.withStreaming()` | SSE Streaming |
| `APIKeyAuth` / `BearerAuth` | Security schemes |

---

## Full API Reference

See [AGENT.md](../../AGENT.md) for the complete multi-language API reference.

---

## License

MIT
