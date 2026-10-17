# A2A Lite — Java

[![GitHub](https://img.shields.io/badge/GitHub-a2a--lite-blue?logo=github)](https://github.com/xvierd/a2a-lite)

> **A2A Lite is designed for learning and prototyping.** It's the friendly on-ramp to Google's A2A Protocol — get familiar with agent-to-agent concepts with minimal boilerplate before diving into the full [a2aproject/a2a-java](https://github.com/a2aproject/a2a-java) SDK. Perfect for courses, POCs, and demos.

**Build A2A agents in 8 lines. Add features when you need them.**

Wraps the official [A2A Java SDK](https://github.com/a2aproject/a2a-java) with a simple, builder-based API and a standalone JSON-RPC adapter.

> **v1.2.0 — A2A Protocol v1.0.** Serves A2A v1.0 (JSON-RPC transport, card at `/.well-known/agent-card.json`) integrated with `org.a2aproject.sdk` 1.4.0.Final via `AgentEmitter`. No v0.3 compatibility. Prepared Maven coordinates: `io.github.xvierd:a2a-lite:1.2.0`. See [MIGRATION.md](../../MIGRATION.md).

The standalone Javalin server started by `agent.run()` uses the official SDK
request handler for messages, SSE streaming, task retrieval/cancellation,
subscriptions, task listing and push configuration. Requests must send
`A2A-Version: 1.0`. The card advertises JSON-RPC and enables streaming when a
streaming skill is registered. The learning default stores protocol tasks and ownership in memory. An explicit
`JdbcProtocolBackend` persists both together with a task-revision journal and callback outbox. REST and gRPC require a separate SDK integration.

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

**Java 1.2.0 is built and verified in this repository, but is not published to Maven Central.** A dependency declaration alone will not download it. Java 17+ is required.

The examples resolve the library directly from the checkout through a Gradle composite build; no publication, credentials or signing key is needed:

```bash
# From the repository root
cd examples/java
./gradlew :01_hello_world_lite:run
```

For another Gradle application, add this to its `settings.gradle`, replacing the path with your checkout location:

```groovy
includeBuild('/absolute/path/to/a2a-lite/packages/java') {
    dependencySubstitution {
        substitute module('io.github.xvierd:a2a-lite') using project(':')
    }
}
```

### Gradle dependencies (with the composite build above)

```groovy
dependencies {
    implementation 'io.github.xvierd:a2a-lite:1.2.0'
    implementation 'io.javalin:javalin:7.2.3'
}
```

### Maven (local installation)

Build the artifacts and install their generated POM in your local Maven repository. These commands do not sign or publish to a remote repository:

```bash
# From the repository root
cd packages/java
./gradlew jar sourcesJar javadocJar generatePomFileForMavenPublication
mvn install:install-file \
  -Dfile=build/libs/java-1.2.0.jar \
  -DpomFile=build/publications/maven/pom-default.xml \
  -Dsources=build/libs/java-1.2.0-sources.jar \
  -Djavadoc=build/libs/java-1.2.0-javadoc.jar
```

Then use these dependencies in your Maven application:

```xml
<dependency>
    <groupId>io.github.xvierd</groupId>
    <artifactId>a2a-lite</artifactId>
    <version>1.2.0</version>
</dependency>

<dependency>
    <groupId>io.javalin</groupId>
    <artifactId>javalin</artifactId>
    <version>7.2.3</version>
</dependency>
```

For Maven, also import `org.eclipse.jetty:jetty-bom:12.1.14` and
`org.eclipse.jetty.ee10:jetty-ee10-bom:12.1.14` and
`com.fasterxml.jackson:jackson-bom:2.22.3` in `dependencyManagement`; Javalin's
bundled Jetty baseline is older. Gradle consumes these constraints from this library.
The standalone adapter now requires Javalin 7.2.3; custom adapters retain the
`ServerAdapter` interface. Routes register before the server starts.

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

// Streaming through the official SDK server integration
agent.skill("stream",
    SkillConfig.withStreaming(),
    params -> StreamingHandler.fromIterator(List.of("Hello ", "World").iterator())
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
// Read the full protocol Task, including its status
Map<String, Object> task = handle.get();
Map<String, Object> task2 = handle.get(15);  // custom timeout in seconds

// Legacy network helpers below return the flattened task result
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
var network = new AgentNetwork();
network.add("worker", "https://worker.example/");
network.withHeaders("https://worker.example/", Map.of("Authorization", "Bearer <token>"));
TaskHandle handle = network.callWithHandle("worker", "process", Map.of("data", "..."), 30);

// Register webhook for this specific task
handle.subscribe("https://my-app.com/webhook");

// Or via network
network.setTaskPushNotification("https://worker.example/", handle.getTaskId(), "https://my-app.com/webhook");

// Retrieve / remove
Object config = handle.getPushConfig();
handle.unsubscribe();
```

Standalone push configuration is managed by the SDK and requires an authenticated
identity that owns an existing protocol task. Each configuration ID is isolated;
get/delete without an ID target the default configuration. Anonymous servers do
not expose task callbacks. `TaskPushRegistry` remains a programmatic legacy API
and does not back the HTTP endpoints.

Client-supplied callback URLs must use HTTPS, contain no credentials or fragment,
and resolve only to public addresses. Delivery revalidates DNS and pins those
addresses through Apache HttpClient while preserving the original Host and TLS
identity. Redirects are disabled. Notifications use `application/a2a+json` and the
callback token uses `X-A2A-Notification-Token`. Server-configured
`WebhookPushNotifier` URLs remain a separate trusted configuration.

`callWithHandle` and `delegateWithHandle` require a real Task response. They fail
clearly if the peer returns only a Message; use `call`/`delegate` for those replies.
`withHeaders` applies headers only to the configured agent endpoint.

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

## OAuth2 verification

`OAuth2Auth` verifies JWT signatures using Nimbus JOSE + JWT (included), a trusted
configured JWKS endpoint and an explicit asymmetric algorithm allowlist (`RS256`
by default). It validates issuer, configured audience, expiry, optional `nbf`, and
a nonempty string `sub`. Unsigned, tampered, expired or identity-less tokens are
rejected; there is no parser-only fallback. Scopes come from token claims and
remain empty when absent. Existing demos using fabricated tokens must switch to
signed tokens from the configured issuer.

## Quarkus Integration

For Quarkus applications, use CDI producer classes to integrate with the framework:

The official SDK 1.4.0.Final denies task operations unless a
`TaskAuthorizationProvider` is configured. Supply a provider for production;
for development or a deliberately open single-user deployment, set
`a2a.authorization.required=false`. This SDK setting applies to the Quarkus
request handler; standalone `agent.run()` maps A2A Lite's configured
`AuthProvider` identity to SDK task ownership. Configured providers must return a
nonempty identity; `NoAuth` and composite anonymous fallbacks cannot register callbacks. See the [official authorization migration notes](https://a2aproject.github.io/a2a-java/posts/a2a-java-sdk-1-3-0-final-released/#2-fail-closed-authorization-default).

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
| `SkillConfig.withStreaming()` | SSE streaming in standalone and SDK integrations |
| `APIKeyAuth` / `BearerAuth` | Security schemes |

---

## Examples

Java samples: [`examples/`](examples/) and the repo-root [side-by-side suite](../../examples/java/).

### Showcase: Battleship (Python demo — same protocol)

Playable multi-agent **A2A v1.0** showcase (Python + a2a-lite; same wire protocol Java agents use):

```bash
# from repo root
cd examples/python/11_battleship_lite
pip install -e ../../../packages/python
python agent.py    # human vs bot → http://localhost:8790/
# python arena.py  # bot vs bot  → http://localhost:8793/?mode=arena
```

Details: [examples/python/11_battleship_lite/README.md](../../examples/python/11_battleship_lite/README.md)

---

## Managed and durable operation

The runnable [production path example](../../examples/java/11_production_path_lite/)
progresses from Message to Task, streaming, authentication, durable state and explicit checkpoint recovery.

```java
var identity = AuthResult.identified("my-service", "alice", Set.of(""), Set.of("work"));
var agent = Agent.builder().name("Worker").description("Bounded service")
    .auth(new APIKeyAuth(Map.of("old-key", identity, "new-key", identity)))
    .runtimeOptions(RuntimeOptions.authenticated()).build();
agent.skill("task", (params, task) -> task.getTaskId());
try (var runtime = agent.start("127.0.0.1", 8787)) {
    runtime.awaitTermination();
}
```

`RuntimeOptions.learning()`, `.authenticated()` and `.durable()` declare intent;
authenticated profiles reject anonymous providers, and durable startup requires a
durable protocol backend. `RuntimeLimits` bounds global and per-principal task/stream
admission, requests, results, retained/query history, callback counts and deadlines.
`maxEventsPerExecution` defaults to 4,096 user chunks/status updates (including empty
ones); TaskContext updates share output bytes and deadline enforcement.
Defaults allow 32 tasks/64 streams globally and 8 tasks/16 streams per identity;
tenants share their identity's admission quota. The learning backend retains at
most 10,000 task/ownership reservations. At capacity it evicts only finalized tasks
older than one second, with their ownership and callback credentials; it never
evicts active/input-required work to admit a new call. Finalized records expire
on the next admission after 24 hours. Message-only reservations are released after
delivery; orphaned owner-only reservations expire after the execution deadline plus
five seconds. Saturation
returns HTTP 503 before allocating SDK task/stream resources. Reads/cancel remain
available. `/health/live`, `/health/ready`, `/metrics`, `runtime.ready()` and
`runtime.metrics()` expose operational state without principal/task labels.

`Agent.start()` installs no process signal hooks. Closing drains and interrupts
remaining work; interruption is cooperative and does not terminate arbitrary Java
code. Adapter/backend cleanup and shutdown hooks share the `shutdownGrace` return
budget. If uncooperative cleanup outlives it, `shutdownCleanupRunning` stays true;
the daemon cleanup thread is interrupted, and the hosting process regains control. `agent.run()` remains the command-line convenience that installs a shutdown
hook. Task slots stay occupied until handlers actually finish.

Credentials can rotate through `network.withCredentials(endpoint, uri -> headers)`.
They apply to discovery and all task-handle requests at that endpoint; redirects
are disabled. `handle.get()` returns the full protocol Task. Legacy `getStatus()`
retains its flattened-result behavior. A Message-only response cannot create a
TaskHandle. Namespaced principals encode `[namespace,subject]` collision-safely;
legacy subjects remain unchanged unless they begin `a2a:v1:` (reserved and escaped).
OAuth namespaces come from the configured verified issuer. Tenant membership is
explicit in `AuthResult.authorizedTenants()`; the default is only the empty tenant.

```java
var backend = new JdbcProtocolBackend(dataSource, callbackKeyring, RuntimeLimits.defaults());
backend.initializeSchema(); // controlled migration step, before application startup
var durable = Agent.builder().name("Worker").description("Persistent tasks")
    .auth(auth).protocolBackend(backend).runtimeOptions(RuntimeOptions.durable()).build();
```

`ProtocolBackend` groups the official SDK task/state stores, authorization, push
store and queue factory so state and ownership cannot silently fall back to memory.
The optional JDBC reference uses PostgreSQL; the application supplies its JDBC driver,
bounded DataSource and AES callback-key ring. Startup validates the active key
configuration, not decryption of every retained callback; verify retained keys
before resuming delivery after a restore. The four-argument constructor with
`automaticDelivery=false` keeps the atomic outbox while pausing automatic outbound
callbacks, for isolated restores or tests; explicit `outbox().drainOnce()` is an
operator-controlled send. The official SDK JPA store remains a
valid Quarkus integration option, but it does not supply this atomic outbox/ownership
boundary automatically.

The JDBC prototype persists task revisions and delivery records atomically. It
supports other-replica Task reads, snapshot subscriptions, cancellation relay, and
5-second execution leases renewed every 500 ms. Expired ordinary workers become
`FAILED` with an interruption message; they are not automatically retried. Each
writer is fenced. Explicit `backend.checkpoints()` workflows can recover a persisted
checkpoint under a new fence; downstream side effects need idempotency/fencing too.
Snapshot subscriptions send current Task first, then committed status/artifact
replacements; they do not reproduce original chunk boundaries or resume arbitrary
handler stacks. Durable callbacks use stable `X-A2A-Delivery-Id`, encrypted
credentials and jittered exponential retry (0.5–300 seconds). Eight claims,
including workers killed before ACK, or 24 hours of delivery age produce a dead
letter. Explicit operator retry preserves the delivery ID and starts a new attempt/age
budget. Delivery remains at least once. A config
delete removes queued work; in-flight delivery can finish. Retention is an explicit
bounded `purgeFinalizedBefore()` operation and protects pending/dead-letter deliveries.
Schedule it explicitly; the durable revision journal has no automatic retention cap.

## Full API Reference

See [AGENT.md](../../AGENT.md) for the complete multi-language API reference.

---

## License

MIT
