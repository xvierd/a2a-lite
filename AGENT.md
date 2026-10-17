# A2A-Lite Agent Reference

Quick reference for AI coding assistants implementing A2A agents.

## Protocol Notes (A2A v1.0 — SDK baseline checked 2026-10-17)

- All three packages serve **A2A protocol v1.0**. There is **no v0.3 compatibility** — lite clients detect 0.3 agent cards and fail with a clear error.
- The latest stable specification is **1.0.1**. Patch versions are documentation/specification revisions; keep **`1.0`** in agent cards and `A2A-Version`, independently of SDK or a2a-lite package versions.
- Agent card is served at `GET /.well-known/agent-card.json` (the old `/.well-known/agent.json` is gone). Card shape: `supportedInterfaces` list, **no root-level `url`/`protocolVersion`**.
- Wire: JSON-RPC methods `SendMessage`, `SendStreamingMessage`, `GetTask`, `CancelTask`, `CreateTaskPushNotificationConfig`, etc., with header `A2A-Version: 1.0`. Parts have **no `kind`/`type` discriminator** — a text part is `{"text": "..."}`. Roles/states are enum-style: `ROLE_USER`, `TASK_STATE_WORKING`, ...
- SDK integration underneath (invisible to lite-API users): Python mounts `a2a-sdk` 1.2.2 **route factories** (`create_agent_card_routes` / `create_jsonrpc_routes` / `create_rest_routes`); TypeScript uses `@a2a-js/sdk` 1.3.0 **express handlers** (`jsonRpcHandler` / `restHandler` / `agentCardHandler`, requires Node >= 20); Java connects its Javalin JSON-RPC adapter to the request handler and event runtime in `org.a2aproject.sdk` 1.4.0.Final through `AgentEmitter` (the 1.x replacement for `EventQueue` + `TaskUpdater`).
- Java standalone `agent.run()` uses official SDK handlers for messaging, SSE, task lifecycle and push configuration over JSON-RPC. REST is not advertised. SDK task authorization must be configured separately for Quarkus (see `MIGRATION.md`). Dynamic push requires authentication and public HTTPS callbacks in every language.
- Java Maven coordinates: `io.github.xvierd:a2a-lite:1.2.0` (source version; Maven Central publication pending). Standalone requires Javalin 7.2.3 on Java 17+ and the BOM alignment in [the Java guide](packages/java/README.md#installation). The `com.a2alite.tasks` package no longer exists — task types live in `com.a2alite.*`.

## 1.2.0 runtime and task contracts

- Python and npm 1.2.0 are published. Java 1.2.0 currently runs from the source/composite builds in `examples/java`.
- Ordinary Message responses do not create a queryable Task. Request task mode with Python `task=True`, TypeScript `{ task: true }`, or Java `SkillConfig.withTask()`. The injected context uses the protocol Task ID; Python `TaskContext` no longer requires an application-local `task_store`.
- Use `learning` for infrastructure-free examples, `authenticated` for verified identities and `durable` with the supported database adapter and external encryption keys. A durable profile validates prerequisites and does not silently fall back to memory.
- Use the managed `start` API and close its returned runtime in `finally`. The host application owns process signals. Cancellation is cooperative; uncooperative work needs process isolation for hard termination.
- Map rotating credentials to a stable principal, and authorize tenant membership before accessing tasks. Send client credentials in headers or a scoped credential provider.
- Durable callbacks are at least once and require receiver deduplication. Arbitrary interrupted functions do not automatically resume: checkpoint recovery is opt-in and language-specific.

See [OPERATIONS.md](OPERATIONS.md), [MIGRATION.md](MIGRATION.md), and the progressive examples for [Python](examples/python/12_production_path/README.md), [TypeScript](examples/typescript/11_production_path/README.md) and [Java](examples/java/11_production_path_lite/README.md).

## Core Pattern

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
<th>Java</th>
</tr>
<tr>
<td>

```python
from a2a_lite import Agent

agent = Agent(
    name="AgentName",
    description="What it does"
)

@agent.skill("skill_name")
async def skill_name(param: str) -> str:
    return f"Result: {param}"

agent.run()
```

</td>
<td>

```typescript
import { Agent } from 'a2a-lite';

const agent = new Agent({
  name: 'AgentName',
  description: 'What it does'
});

agent.skill('skill_name', async ({ param }) =>
  `Result: ${param}`
);

agent.run();
```

</td>
<td>

```java
var agent = Agent.builder()
    .name("AgentName")
    .description("What it does")
    .build();

agent.skill("skill_name", params ->
    "Result: " + params.get("param")
);

agent.run();
```

</td>
</tr>
</table>

## Imports by Feature

### Python
```python
# Core (always needed)
from a2a_lite import Agent

# Testing
from a2a_lite import AgentTestClient

# Optional features (import only when needed)
from a2a_lite import FilePart, DataPart, Artifact      # Multi-modal
from a2a_lite import TaskContext                        # Task lifecycle
from a2a_lite.auth import APIKeyAuth, BearerAuth       # Authentication
from a2a_lite.auth import AuthResult                   # Auth injection
```

### TypeScript
```typescript
// Core (always needed)
import { Agent } from 'a2a-lite';

// Testing
import { AgentTestClient } from 'a2a-lite';

// Optional features
import { FilePart, DataPart, Artifact } from 'a2a-lite';    // Multi-modal
import { APIKeyAuth, BearerAuth } from 'a2a-lite';          // Authentication
```

### Java
```java
// Core (always needed)
import com.a2alite.Agent;

// Testing
import com.a2alite.testing.AgentTestClient;

// Optional features
import com.a2alite.SkillConfig;                  // Skill configuration
import com.a2alite.auth.APIKeyAuth;              // API key auth
import com.a2alite.auth.BearerAuth;              // Bearer token auth
```

## Feature Detection (Python)

Features are auto-detected from type hints:

| Type Hint | Auto-Enabled Feature |
|-----------|---------------------|
| `task: TaskContext` | Task lifecycle tracking |
| `auth: AuthResult` | Auth result injection |
| `file: FilePart` | File handling |
| `data: DataPart` | Structured data |
| `model: PydanticModel` | Auto-conversion |

## Quick Patterns

### 1. Basic Skill
```python
@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"
```

### 2. Pydantic Model (auto-converted)
```python
from pydantic import BaseModel

class Order(BaseModel):
    item: str
    quantity: int

@agent.skill("process")
async def process(order: Order) -> dict:
    return {"item": order.item, "total": order.quantity * 10}
```

### 3. Streaming
```python
@agent.skill("stream", streaming=True)
async def stream(text: str):
    for word in text.split():
        yield word
```

### 4. File Handling
```python
from a2a_lite import FilePart

@agent.skill("analyze")
async def analyze(file: FilePart) -> dict:
    content = await file.read_text()  # or file.read_bytes()
    return {"name": file.name, "size": len(content)}
```

### 5. Task Progress
```python
from a2a_lite import TaskContext

agent = Agent(name="Bot", description="...")

@agent.skill("process")
async def process(data: str, task: TaskContext) -> dict:
    await task.update("working", "Step 1", progress=0.5)
    return {"done": True, "task_id": task.task_id}
```

### 6. Authentication
```python
from a2a_lite import Agent
from a2a_lite.auth import APIKeyAuth

agent = Agent(
    name="SecureBot",
    description="...",
    auth=APIKeyAuth(keys=["secret-key-123"]),
)
```

### 7. Auth Result Injection
```python
from a2a_lite.auth import AuthResult

@agent.skill("whoami")
async def whoami(auth: AuthResult) -> dict:
    return {"user": auth.user_id, "namespace": auth.namespace}
```

### 8. Middleware
```python
@agent.middleware
async def log_calls(ctx, next):
    print(f"Calling: {ctx.skill}")
    result = await next()
    print(f"Result: {result}")
    return result
```

### 9. Multi-Part Artifact Output
```python
from a2a_lite.parts import Artifact, FilePart

@agent.skill("generate")
async def generate(query: str) -> Artifact:
    return (
        Artifact(name="report")
        .add_text("Summary here")
        .add_data({"count": 42})
        .add_file(FilePart(name="data.csv", data=b"a,b,c\n1,2,3"))
    )
```

## Testing

### Python
```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)

# With auth headers (sent with every request)
client = AgentTestClient(agent, headers={"X-API-Key": "secret-key-123"})

# Regular call
result = client.call("skill_name", param="value")

# Streaming (collects all)
results = client.stream("streaming_skill", param="value")

# List skills
skills = client.list_skills()

# Get agent card
card = client.get_agent_card()
```

### TypeScript
```typescript
import { AgentTestClient } from 'a2a-lite';

const client = new AgentTestClient(agent);

// Regular call
const result = await client.call('skill_name', { param: 'value' });

// Streaming (collects all)
const results = await client.stream('streaming_skill', { param: 'value' });

// List skills
const skills = client.listSkills();

// Get agent card
const card = client.getAgentCard();
```

### Java
```java
import com.a2alite.testing.AgentTestClient;
import java.util.Map;

var client = new AgentTestClient(agent);

// Regular call
var result = client.call("skill_name", Map.of("param", "value"));

// List skills
List<String> skills = client.listSkills();

// Get agent card
ObjectNode card = client.getAgentCard();
```

## Agent Constructor Options

### Python
```python
agent = Agent(
    name="Bot",              # Required
    description="...",       # Required
    version="1.0.0",         # Optional, default "1.0.0"
    url=None,                # Optional, auto-detected
    auth=None,               # Optional: APIKeyAuth, BearerAuth, etc.
    task_store=None,         # Optional application-local mirror, not protocol persistence
    runtime=None,            # Optional RuntimeConfig; default learning profile
    persistence=None,        # Optional PersistenceConfig for durable protocol state
    cors_origins=None,       # Optional: list of allowed origins
    production=False,        # Optional: enable production warnings
)
```

### TypeScript
```typescript
const agent = new Agent({
  name: 'Bot',              // Required
  description: '...',       // Required
  version: '1.0.0',         // Optional, default "1.0.0"
  url: undefined,           // Optional, auto-detected
  auth: undefined,          // Optional: APIKeyAuth, BearerAuth, etc.
  profile: 'learning',      // authenticated and durable validate prerequisites
  persistence: undefined,  // Optional PostgreSQL protocol adapter
});
```

### Java
```java
var agent = Agent.builder()
    .name("Bot")            // Required
    .description("...")     // Required
    .version("1.0.0")       // Optional, default "1.0.0"
    .url(null)              // Optional, auto-detected
    .auth(new APIKeyAuth(...)) // Optional
    .build();
```

## Run Options

### Python
```python
agent.run(
    host="0.0.0.0",          # Default
    port=8787,               # Default
    log_level="info",        # Logging
)
```

### TypeScript
```typescript
agent.run({
  host: '0.0.0.0',          // Default
  port: 8787,               // Default
});
```

### Java
```java
agent.run();           // Default port 8787
agent.run(9000);       // Custom port
agent.run("localhost", 9000);  // Custom host and port
```

## Lifecycle Hooks

### Python
```python
@agent.on_startup
async def startup():
    print("Agent starting")

@agent.on_shutdown
async def shutdown():
    print("Agent stopping")

@agent.on_complete
async def completed(skill_name, result, ctx):
    print(f"Completed: {skill_name}")

@agent.on_error
async def error_handler(e: Exception) -> dict:
    return {"error": str(e)}
```

### TypeScript
```typescript
agent.onStartup(() => console.log('Agent starting'));
agent.onShutdown(() => console.log('Agent stopping'));
agent.onComplete((skill, result) => console.log(`Completed: ${skill}`));
agent.onError(async (e) => ({ error: e.message }));
```

### Java
```java
agent.onStartup(() -> System.out.println("Agent starting"));
agent.onShutdown(() -> System.out.println("Agent stopping"));
agent.onComplete((skill, result) -> System.out.println("Completed: " + skill));
agent.onError(e -> Map.of("error", e.getMessage()));
```

## Auth Providers

### Python
```python
# Header API keys mapped to a stable owner across rotation
APIKeyAuth(principals={"key1": "user-1", "key2": "user-1"}, header="X-API-Key")

# Bearer token with custom validator
BearerAuth(validator=lambda token: "user-id" if valid(token) else None)

# Multiple auth methods
CompositeAuth([APIKeyAuth(...), BearerAuth(...)])
```

### TypeScript
```typescript
import { APIKeyAuth, BearerAuth } from 'a2a-lite';

// API Key
new APIKeyAuth({ keys: new Set(['key1', 'key2']), header: 'X-API-Key' })

// Bearer token
new BearerAuth({ validator: async (token) => valid(token) ? 'user-id' : null })
```

### Java
```java
import com.a2alite.auth.APIKeyAuth;
import com.a2alite.auth.BearerAuth;

// API Key
new APIKeyAuth(Set.of("key1", "key2"))

// Bearer token
new BearerAuth(token -> valid(token) ? "user-id" : null)
```

## Task States

```python
from a2a_lite.tasks import TaskState

TaskState.SUBMITTED      # Initial state
TaskState.WORKING        # In progress
TaskState.INPUT_REQUIRED # Waiting for user
TaskState.COMPLETED      # Done
TaskState.FAILED         # Error
TaskState.CANCELED       # Cancelled
```

## File Formats

```python
# Creating FilePart
FilePart(name="file.txt", data=b"content")           # From bytes
FilePart(name="file.txt", data="text content")       # From string (auto-encoded)
FilePart(name="file.txt", uri="https://...")         # From URL
FilePart.from_path("/path/to/file.txt")              # From local file

# Reading FilePart
content = await file.read_text()      # As string
content = await file.read_bytes()     # As bytes
```

## Common Mistakes

### Python
1. **Forgetting async**: Skills should be `async def`
2. **Confusing Message and Task**: use `task=True` or a `TaskContext` parameter for queryable tasks; no separate `task_store` is required
3. **Wrong import**: `from a2a_lite import X` not `from a2a_lite.module import X` for core features
4. **Streaming without flag**: Use `@agent.skill("name", streaming=True)` for generators

### TypeScript
1. **Missing await**: Async skill handlers return Promises
2. **Wrong type**: Skill handlers receive `Record<string, unknown>`, cast as needed
3. **Express peer dependency**: Install Express separately for standalone mode

### Java
1. **Missing builder `.build()`**: Agent uses builder pattern, don't forget `.build()`
2. **Javalin dependency**: For standalone mode, add `io.javalin:javalin` dependency
3. **Quarkus integration**: For Quarkus, use `agent.getExecutor()` with CDI producers

## A2A Protocol Mapping

| A2A-Lite | A2A Protocol |
|----------|--------------|
| `@agent.skill()` / `agent.skill()` | AgentSkill |
| `streaming=True` / `SkillConfig.withStreaming()` | SSE streaming |
| `TaskContext` | Task lifecycle |
| `FilePart` | A2A FilePart |
| `DataPart` | A2A DataPart |
| `Artifact` | A2A Artifact |
| `APIKeyAuth` / `BearerAuth` | Security schemes |

## Middleware

### Python
```python
@agent.middleware
async def log_calls(ctx, next):
    print(f"Calling: {ctx.skill}")
    result = await next()
    print(f"Result: {result}")
    return result
```

### TypeScript
```typescript
agent.use(async (ctx, next) => {
  console.log(`Calling: ${ctx.skill}`);
  const result = await next();
  console.log(`Result: ${result}`);
  return result;
});
```

### Java
```java
agent.use((ctx, next) -> {
    System.out.println("Calling: " + ctx.skill());
    Object result = next.call();
    System.out.println("Result: " + result);
    return result;
});
```

## Skill Configuration

### Python
```python
@agent.skill("greet", description="Greet someone", tags=["greeting"])
async def greet(name: str) -> str:
    return f"Hello, {name}!"

@agent.skill("stream", streaming=True)
async def stream(text: str):
    for word in text.split():
        yield word
```

### TypeScript
```typescript
agent.skill('greet', {
  description: 'Greet someone',
  tags: ['greeting']
}, async ({ name }) => `Hello, ${name}!`);

agent.skill('stream', { streaming: true }, async function* ({ text }) {
  for (const word of String(text).split(' ')) {
    yield word;
  }
});
```

### Java
```java
agent.skill("greet",
    SkillConfig.of("Greet someone", List.of("greeting")),
    params -> "Hello, " + params.get("name") + "!"
);

agent.skill("stream",
    SkillConfig.withStreaming(),
    params -> com.a2alite.streaming.StreamingHandler.fromIterator(List.of("one", "two").iterator())
);
```
