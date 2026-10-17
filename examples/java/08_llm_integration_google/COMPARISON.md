# Java LLM examples: manual server and Lite simulation

The `08_llm_integration_google` name is historical: it is a hand-written A2A v1.0 server using Javalin 7.2.3 and Jackson, not an implementation built on the official A2A Java SDK. A2A Lite uses SDK 1.4.0.Final underneath its standalone adapter.

These examples have different behavior. The manual example contains an HTTP provider client; the Lite example simulates responses. A line-count comparison therefore does not measure equivalent functionality or production readiness.

| Concern | Manual example | Lite example |
|---------|----------------|--------------|
| Build | Maven, `pom.xml` | Gradle, local composite build |
| A2A transport | Application-built JSON-RPC routes/card | Library adapter and SDK handler |
| LLM calls | Custom OpenAI/Anthropic HTTP client | No provider call; simulated response |
| Tool selection | Explicit tool registry | Keyword matching for calculator/time/mock weather |
| Session history | Example-managed conversation manager | Example-managed map and recent-message trimming |
| Durable protocol tasks | Not configured | Not configured in this sample |
| Multi-user business-state isolation | Must be designed by the application | Session IDs alone are not authorization |

## Server setup

The manual server registers routes with Javalin 7 before startup:

```java
Javalin app = Javalin.create(config -> {
    config.startup.showJavalinBanner = false;
    config.routes.get("/.well-known/agent-card.json", ctx -> ctx.json(agentCard));
    config.routes.post("/", ctx -> handleRequest(ctx));
});
app.start(8793);
```

Lite handles the transport when registered skills run:

```java
agent.skill("chat", params -> handleChat(params));
agent.run(8794);
```

The application still owns `handleChat`, session isolation, concurrency safety, retention, provider credentials and any external side effects. Adding a JDBC protocol backend does not automatically persist these application maps.

## Run the Lite simulation

Java 1.2.0 is built and verified in the repository but not published to Maven Central. Run with the included composite build:

```bash
# From the repository root
cd examples/java
OPENAI_API_KEY=simulation-only ./gradlew :08_llm_integration_lite:run
```

The environment variable only passes the demo's presence check; it is not used to make a provider request. For actual provider calls, follow the [manual example README](README.md) with your own credentials and an available model. Those external calls are not part of the repository verification.

For the supported progression through real Task IDs, SSE, stable identities and durable state, use [example 11](../11_production_path_lite/). Its [operational guide](../../../OPERATIONS.md) documents tested boundaries and remaining application responsibilities. Neither comparison is an enterprise certification.
