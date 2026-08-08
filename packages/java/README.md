# A2A Lite — Java

[![GitHub](https://img.shields.io/badge/GitHub-a2a--lite-blue?logo=github)](https://github.com/xvierd/a2a-lite)

> **A2A Lite is designed for learning and prototyping.** It's the friendly on-ramp to Google's A2A Protocol — get familiar with agent-to-agent concepts with minimal boilerplate before diving into the full [google/a2a-java](https://github.com/a2aproject/a2a-java) SDK. Perfect for courses, POCs, and demos.

**Build A2A agents in 8 lines. Add features when you need them.**

Wraps the official [A2A Java SDK](https://github.com/a2aproject/a2a-java) with a simple, builder-based API. 100% protocol-compatible.

> **v1.0.0 — A2A Protocol v1.0.** Serves A2A v1.0 (JSON-RPC transport, card at `/.well-known/agent-card.json`) integrated with `org.a2aproject.sdk` 1.1.0.Final via `AgentEmitter`. No v0.3 compatibility. New Maven coordinates: `io.github.xvierd:a2a-lite:1.0.0`. See [MIGRATION.md](../../MIGRATION.md).

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
    implementation 'io.github.xvierd:a2a-lite:1.0.0'
    implementation 'io.javalin:javalin:5.6.3'
}
```

### Maven

```xml
<dependency>
    <groupId>io.github.xvierd</groupId>
    <artifactId>a2a-lite</artifactId>
    <version>1.0.0</version>
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

## Multi-Agent Communication

### TaskHandle — track remote tasks

`delegateWithHandle` returns a `TaskHandle` carrying the remote task ID so you can poll or cancel later:

```java
AgentNetwork network = new AgentNetwork();
network.add("data", "http://localhost:8787");

Agent agent = Agent.builder()
    .name("Orchestrator")
    .description("Orchestrates work across agents")
    .network(network)
    .build();

agent.skill("process", params -> {
    String query = (String) params.get("query");

    // Get a TaskHandle instead of just the result
    TaskHandle handle = agent.delegateWithHandle("data", "fetch",
        Map.of("query", query));

    System.out.println("Task ID: " + handle.getTaskId());
    System.out.println("Result: " + handle.getResult());
    return handle.getResult();
});
```

#### Task Lifecycle — poll and cancel remote tasks

Use convenience methods directly on the handle, or via the network by name:

```java
// Poll status directly on the handle
Object status = handle.getStatus();
Object status2 = handle.getStatus(15);  // custom timeout in seconds

// Or poll via network name
Object status3 = network.getTask("data", handle.getTaskId());
Object status4 = network.getTask("data", handle.getTaskId(), 15);

// Cancel directly on the handle
handle.cancel();
handle.cancel(15);

// Or cancel via network name
network.cancelTask("data", handle.getTaskId());
network.cancelTask("data", handle.getTaskId(), 15);
```

Low-level functions are also available:

```java
Object status = network.getRemoteTask("http://localhost:8787", taskId, 10);
Object result = network.cancelRemoteTask("http://localhost:8787", taskId, 10);
```

### Client-Side SSE Streaming

When calling a remote streaming agent, consume its chunks as they arrive:

```java
// Via agent.streamDelegate
StreamingHandler.StreamResult stream = agent.streamDelegate(
    "story", "tell_story", Map.of("topic", "dragons"));

for (Object chunk : stream) {
    System.out.print(chunk);
    System.out.flush();
}

// Or directly via AgentNetwork
StreamingHandler.StreamResult stream = network.streamRemoteSkill(
    "http://localhost:8787", "tell_story", Map.of("topic", "dragons"));

for (Object chunk : stream) {
    System.out.print(chunk);
}
```

The remote agent must support streaming (declared via `SkillConfig.withStreaming()`). The stream automatically stops when the remote agent finishes or on terminal states.

### Agent Card Discovery

Fetch a remote agent's capabilities from its `/.well-known/agent-card.json` endpoint:

```java
// Fetch an agent's capabilities
AgentCardInfo card = network.discoverAgent("http://localhost:8787");
System.out.println("Agent: " + card.getName() + " v" + card.getVersion());
System.out.println("Skills: " + card.getSkills().size());
System.out.println("Streaming: " + card.isSupportsStreaming());

// Auto-discover when registering
network.add("data", "http://localhost:8787", true);

// Get cached card
Optional<AgentCardInfo> cached = network.getCard("data");

// Discover a named agent
AgentCardInfo namedCard = network.discoverNamed("data");
```

### Per-Task Push Notifications

```java
TaskHandle handle = agent.delegateWithHandle("worker", "process", Map.of("data", "..."));

// Register webhook for this specific task
handle.subscribe("https://my-app.com/webhook");

// Or via network
network.setTaskPushNotification("http://localhost:8787", handle.getTaskId(), "https://my-app.com/webhook");

// Retrieve / remove
Object config = handle.getPushConfig();
handle.unsubscribe();
```

The `TaskPushRegistry` is automatically created on every Agent and handles the v1.0 `CreateTaskPushNotificationConfig` / `GetTaskPushNotificationConfig` / `DeleteTaskPushNotificationConfig` JSON-RPC methods.

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
