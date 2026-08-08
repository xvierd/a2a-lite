<p align="center">
  <h1 align="center">A2A Lite</h1>
  <p align="center">
    <strong>The simplest way to build agents for Google's A2A Protocol.</strong><br>
    Python · TypeScript · Java
  </p>
  <p align="center">
    <a href="https://pypi.org/project/a2a-lite/"><img src="https://img.shields.io/pypi/v/a2a-lite?label=PyPI&logo=pypi&logoColor=white" alt="PyPI"></a>
    <a href="https://pypi.org/project/a2a-lite/"><img src="https://img.shields.io/pypi/pyversions/a2a-lite?logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  </p>
  <p align="center">
    <a href="#installation">Installation</a> &bull;
    <a href="#quick-start">Quick Start</a> &bull;
    <a href="#features">Features</a> &bull;
    <a href="#multi-language-examples">Examples</a> &bull;
    <a href="#feature-matrix">Feature Matrix</a> &bull;
    <a href="ROADMAP.md">Roadmap</a>
  </p>
</p>

> **A2A Lite is designed for learning and prototyping.** It's the friendly on-ramp to Google's A2A Protocol — get familiar with agent-to-agent concepts with minimal boilerplate before going deeper with the official SDKs. Perfect for courses, POCs, and demos. When you're ready for production, the skills you learn here transfer directly.

---

A2A Lite wraps the official A2A SDKs ([Python](https://github.com/a2aproject/a2a-python), [TypeScript](https://github.com/a2aproject/a2a-js), [Java](https://github.com/a2aproject/a2a-java)) to give you a decorator-based API that stays **100% protocol-compatible** with zero boilerplate.

> **v1.0.0 — A2A Protocol v1.0.** All three packages now serve **A2A protocol v1.0** on the official 1.x SDKs (`a2a-sdk 1.1.2`, `@a2a-js/sdk 1.0.1`, `a2a-java-sdk 1.1.0.Final`). v0.3 is **not** compatible — agents on 0.3 and 1.0 cannot call each other. The lite API is unchanged, so most agents migrate by just bumping the dependency. See [MIGRATION.md](MIGRATION.md) for breaking changes and SDK equivalence tables.

## Why A2A Lite?

|  | Official A2A SDK | A2A Lite |
|---|---|---|
| Hello World | ~80 lines, 3 files | **8 lines, 1 file** |
| JSON schemas | Write by hand | **Auto-generated from types** |
| Skill registration | Implement interfaces | **One decorator / method call** |
| LLM integration | You wire it | **Built-in OpenAI / Anthropic / Ollama / Bedrock** |
| Multi-agent | Manual HTTP + JSON-RPC | **`AgentNetwork` + `delegate()`** |
| Testing | Spin up a real HTTP server | **In-process `AgentTestClient`** |
| CLI tools | — | **init · create · serve · inspect · info · test · discover · doctor** |

---

## Installation

### Python
```bash
pip install a2a-lite
# or
uv add a2a-lite
```

### TypeScript / Node.js
```bash
npm install a2a-lite
```

### Java (Gradle)
```groovy
dependencies {
    implementation 'io.github.xvierd:a2a-lite:1.0.1'
    implementation 'io.javalin:javalin:5.6.3'   // HTTP server
}
```

---

## Quick Start

<table>
<tr><th>Python</th><th>TypeScript</th><th>Java</th></tr>
<tr>
<td>

```python
from a2a_lite import Agent

agent = Agent(
    name="Greeter",
    description="Greets people"
)

@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

agent.run()  # http://localhost:8787
```

</td>
<td>

```typescript
import { Agent } from 'a2a-lite';

const agent = new Agent({
  name: 'Greeter',
  description: 'Greets people',
});

agent.skill('greet', async ({ name }) =>
  `Hello, ${name}!`
);

agent.run(); // http://localhost:8787
```

</td>
<td>

```java
var agent = Agent.builder()
    .name("Greeter")
    .description("Greets people")
    .build();

agent.skill("greet", params ->
    "Hello, " + params.get("name") + "!"
);

agent.run(); // http://localhost:8787
```

</td>
</tr>
</table>

That's it. A fully A2A-compliant agent, discoverable by any A2A v1.0 client, serving:
- `POST /` — JSON-RPC `SendMessage` (plus `SendStreamingMessage`, `GetTask`, `CancelTask`, push-notification config methods)
- REST (HTTP+JSON) endpoints — Python and TypeScript (Java: planned; card may advertise `HTTP+JSON`)
- gRPC — Python experimental (`a2a-lite[grpc]`, `agent.run_grpc()`); not enabled by default with `agent.run()`
- `GET /.well-known/agent-card.json` — Agent card with auto-generated skill schemas

---

## Features

### Basic Skills — Just Return a Value

```python
@agent.skill("calculate")
async def calculate(a: float, b: float, op: str) -> float:
    ops = {"+": a + b, "-": a - b, "*": a * b, "/": a / b}
    return ops[op]
```

### Pydantic Models — Schemas for Free

Input/output schemas are generated automatically from your type hints:

```python
from pydantic import BaseModel

class SearchRequest(BaseModel):
    query: str
    limit: int = 10

class SearchResult(BaseModel):
    items: list[str]
    total: int

@agent.skill("search")
async def search(req: SearchRequest) -> SearchResult:
    return SearchResult(items=["result1"], total=1)
```

### Streaming — Just `yield`

```python
@agent.skill("chat", streaming=True)
async def chat(message: str):
    tokens = ["Hello", ", ", "world", "!"]
    for token in tokens:
        yield token
```

### Middleware — Cross-Cutting Concerns

```python
@agent.middleware
async def log_requests(ctx, next):
    print(f"→ {ctx.skill}({ctx.params})")
    result = await next()
    print(f"← {ctx.skill}: {result}")
    return result
```

### File Handling — Upload & Process Files

```python
from a2a_lite import FilePart

@agent.skill("summarize")
async def summarize(doc: FilePart) -> str:
    content = await doc.read_text()
    return f"Summary of {doc.name}: {content[:200]}..."
```

### Task Tracking — Long-Running Operations

```python
from a2a_lite import TaskContext

agent = Agent(name="Processor", description="...", task_store="memory")

@agent.skill("process")
async def process(data: str, task: TaskContext) -> str:
    await task.update("working", "Loading data...", progress=0.0)
    # ... do work ...
    await task.update("working", "Processing...", progress=0.5)
    # ... more work ...
    return "Done!"
```

### Authentication — API Key, Bearer, OAuth2

```python
from a2a_lite import Agent, APIKeyAuth, BearerAuth, OAuth2Auth

# API Key
agent = Agent(name="Bot", description="...", auth=APIKeyAuth(keys=["sk-..."]))

# Bearer / JWT
agent = Agent(name="Bot", description="...", auth=BearerAuth(tokens=["my-token"]))

# OAuth2 (JWT validation)
agent = Agent(
    name="Bot",
    description="...",
    auth=OAuth2Auth(
        issuer="https://accounts.google.com",
        audience="my-api",
    )
)
```

Access auth info inside a skill:

```python
from a2a_lite import AuthResult

@agent.skill("profile")
async def profile(auth: AuthResult) -> dict:
    return {"user_id": auth.subject, "claims": auth.claims}
```

### AgentNetwork — Multi-Agent Orchestration

Connect agents and delegate work across a network:

```python
from a2a_lite import Agent, AgentNetwork

# Define the network
network = AgentNetwork()
network.add("weather", "http://localhost:8788")
network.add("hotels", "http://localhost:8789")

orchestrator = Agent(
    name="TravelAgent",
    description="Plans trips",
    network=network,
)

@orchestrator.skill("plan_trip")
async def plan_trip(city: str) -> dict:
    weather = await orchestrator.delegate("weather", "forecast", {"city": city})
    hotels = await orchestrator.delegate("hotels", "search", {"city": city})
    return {"weather": weather, "hotels": hotels}
```

Call remote agents directly:

```python
from a2a_lite import callRemoteSkill  # Python: AgentNetwork.call()

result = await network.call("weather", "forecast", {"city": "Paris"})
```

#### TaskHandle and Agent Card Discovery

Track remote tasks and discover agent capabilities before calling them:

**Python:**
```python
handle = await agent.delegate("data", "fetch", query="hello", return_handle=True)
print(handle.task_id)  # track the remote task
print(handle.agent_url)  # remote agent URL

status = await handle.get_status()  # poll task lifecycle
await handle.cancel()               # cancel if needed

card = await discover("http://localhost:8787")
print(card.skills)  # inspect before calling
```

**TypeScript:**
```typescript
const handle = await agent.delegate('data', 'fetch', { query: 'hello' }, { returnHandle: true }) as TaskHandle;
console.log(handle.taskId);
console.log(handle.agentUrl);

const status = await handle.getStatus();  // poll task lifecycle
await handle.cancel();                    // cancel if needed

const card = await discoverAgent('http://localhost:8787');
console.log(card.skills);
```

**Java:**
```java
TaskHandle handle = agent.delegateWithHandle("data", "fetch", Map.of("query", "hello"));
System.out.println(handle.getTaskId());

Object status = handle.getStatus();  // poll task lifecycle
handle.cancel();                     // cancel if needed

AgentCardInfo card = network.discoverAgent("http://localhost:8787");
System.out.println(card.getSkills());
```

#### Client-Side SSE Streaming

Consume a remote streaming agent's response chunk by chunk:

**Python:**
```python
# Consume a remote streaming agent's response chunk by chunk
async for chunk in agent.delegate("story", "tell_story", topic="dragons", stream=True):
    print(chunk, end="", flush=True)
```

**TypeScript:**
```typescript
for await (const chunk of await agent.delegate('story', 'tellStory', { topic: 'dragons' }, { stream: true }) as AsyncGenerator<string>) {
  process.stdout.write(chunk);
}
```

**Java:**
```java
for (Object chunk : agent.streamDelegate("story", "tell_story", Map.of("topic", "dragons"))) {
    System.out.print(chunk);
}
```

#### Per-Task Push Notifications

Register a webhook for a specific task — fired when that task completes:

**Python:** `await handle.subscribe("https://my-app.com/webhook")`
**TypeScript:** `await handle.subscribe('https://my-app.com/webhook')`
**Java:** `handle.subscribe("https://my-app.com/webhook")`

### LLM Integration — OpenAI, Anthropic, Ollama, Bedrock

Drop in LLM-powered skills without wiring SDKs manually:

```python
from a2a_lite import Agent
from a2a_lite.llm import openai_skill, anthropic_skill, ollama_skill

agent = Agent(name="AIBot", description="LLM-powered agent")

# OpenAI
agent.register_skill(
    openai_skill(
        name="chat",
        model="gpt-4o",
        system_prompt="You are a helpful assistant.",
    )
)

# Anthropic Claude
agent.register_skill(
    anthropic_skill(
        name="analyze",
        model="claude-opus-4-6",
        system_prompt="Analyze the following text.",
    )
)

# Ollama (local)
agent.register_skill(
    ollama_skill(name="generate", model="llama3")
)
```

TypeScript equivalent:

```typescript
import { Agent, openaiSkill, anthropicSkill, ollamaSkill } from 'a2a-lite';

const agent = new Agent({ name: 'AIBot', description: 'LLM-powered agent' });

agent.skill('chat', openaiSkill({
  model: 'gpt-4o',
  systemPrompt: 'You are a helpful assistant.',
}));

agent.skill('analyze', anthropicSkill({
  model: 'claude-opus-4-6',
  systemPrompt: 'Analyze the following text.',
}));
```

### MCP Tools — Model Context Protocol

Connect agents to MCP servers to access external tools and resources:

```python
from a2a_lite import Agent, MCPClient

agent = Agent(name="ToolAgent", description="Uses external tools")
agent.add_mcp_server("filesystem", "http://localhost:3001/sse")
agent.add_mcp_server("github", "http://localhost:3002/sse")

@agent.skill("file_summary")
async def file_summary(path: str, mcp: MCPClient) -> str:
    content = await mcp.call_tool("filesystem", "read_file", {"path": path})
    return f"File at {path}: {content[:200]}"
```

TypeScript equivalent:

```typescript
import { Agent, MCPClient } from 'a2a-lite';

const agent = new Agent({ name: 'ToolAgent', description: 'Uses external tools' });
agent.addMcpServer('filesystem', 'http://localhost:3001/sse');

agent.skill('file_summary', async ({ path }, { mcp }) => {
  const content = await mcp.callTool('filesystem', 'read_file', { path });
  return `File: ${content.slice(0, 200)}`;
});
```

### Router — Multiple Agents, One Server

Mount several agents under a single URL:

```python
from a2a_lite import Router

router = Router()
router.mount("/weather", weather_agent)
router.mount("/hotels", hotel_agent)
router.mount("/flights", flight_agent)

router.run(port=8787)
# Merged card at /.well-known/agent-card.json
# Each agent at /weather, /hotels, /flights
```

### Tool Schemas — Use Your Agent as LLM Tools

Export skill definitions in OpenAI or Anthropic tool format:

```python
# OpenAI format (default)
tools = agent.get_tool_schemas()

response = openai.chat.completions.create(
    model="gpt-4o",
    messages=messages,
    tools=tools,   # ← drop in directly
)

# Anthropic format
tools = agent.get_tool_schemas(format="anthropic")
```

---

## Testing

Every language ships an in-process `AgentTestClient` — no HTTP server needed.

<table>
<tr><th>Python</th><th>TypeScript</th><th>Java</th></tr>
<tr>
<td>

```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)

# Sync call
result = client.call("greet", name="World")
assert result == "Hello, World!"

# Async call
result = await client.acall("greet", name="World")

# Streaming
chunks = await client.stream("chat", message="Hi")
```

</td>
<td>

```typescript
import { AgentTestClient } from 'a2a-lite';

const client = new AgentTestClient(agent);

const result = await client.call('greet', { name: 'World' });
expect(result.data).toBe('Hello, World!');

// Streaming
const chunks = await client.stream('chat', { message: 'Hi' });

// Inspect the agent
const skills = client.listSkills();
const card = client.getAgentCard();
```

</td>
<td>

```java
var client = new AgentTestClient(agent);

var result = client.call("greet", Map.of("name", "World"));
assertThat(result.data()).isEqualTo("Hello, World!");

// No params
var result2 = client.call("ping");

// Inspect
List<String> skills = client.listSkills();
```

</td>
</tr>
</table>

---

## CLI

The Python package ships a full CLI. Full reference: [`packages/python/docs/cli.md`](packages/python/docs/cli.md).

```bash
a2a-lite init my-agent                          # Scaffold a basic project
a2a-lite create my-agent                        # Full project + tests + Docker
a2a-lite serve agent.py                         # Run an agent from a .py file
a2a-lite inspect http://localhost:8787          # Rich agent card + skills
a2a-lite info http://localhost:8787             # Compact plain-text info
a2a-lite test http://localhost:8787 greet -p name=World
a2a-lite discover http://localhost:8787 http://localhost:8788
a2a-lite doctor                                 # Local env (SDK, extras)
a2a-lite doctor http://localhost:8787           # + verify remote speaks A2A v1.0
a2a-lite version
```

TypeScript (`npx a2a-lite`): `init`, `inspect`, `info`, `test`, `discover`, `doctor`.
---

## A2A v1.0

Since a2a-lite 1.0.0, all three packages serve **A2A protocol v1.0** on the official 1.x SDKs:

- **JSON-RPC transport** — Python, TypeScript, Java.
- **REST (HTTP+JSON) transport** — Python and TypeScript (served); Java advertises the binding on the card but only serves JSON-RPC today.
- **gRPC transport** — Python **experimental** (`pip install a2a-lite[grpc]`, `agent.run_grpc()`); TypeScript/Java planned.
- **SSE streaming**, **per-task push notifications** (`TaskPushNotificationConfig`), and **`securitySchemes` in the agent card** — all three languages.
- **Signed Agent Cards** — TypeScript (experimental, `signAgentCard` / `verifyAgentCard`); Python/Java planned.
- Agent card served at **`/.well-known/agent-card.json`** (the old `agent.json` path is gone).
- **No v0.3 compatibility** — lite clients detect 0.3 cards and fail with a clear error.

Migrating from a2a-lite 0.3.x? The lite API is unchanged — most agents only need a dependency bump. See [MIGRATION.md](MIGRATION.md) for breaking changes, per-language steps, and SDK 0.3 → 1.x equivalence tables.

---

## Feature Matrix

| Feature | Python | TypeScript | Java |
|---|:---:|:---:|:---:|
| **Protocol (A2A v1.0)** | | | |
| A2A protocol v1.0 | ✅ | ✅ | ✅ |
| JSON-RPC transport | ✅ | ✅ | ✅ |
| REST (HTTP+JSON) transport | ✅ | ✅ | 🔜 planned¹ |
| gRPC transport | ✅ experimental² | 🔜 planned | 🔜 planned |
| `securitySchemes` in agent card | ✅ | ✅ | ✅ |
| Signed Agent Cards | 🔜 planned | ✅ experimental | 🔜 planned |
| `ListTasks` | 🔜 planned | 🔜 planned | 🔜 planned |
| Multi-tenancy | 🔜 planned | 🔜 planned | 🔜 planned |
| v0.3 compatibility | ❌ | ❌ | ❌ |
| **Lite API** | | | |
| Basic skills | ✅ | ✅ | ✅ |
| Auto JSON schemas | ✅ Pydantic | ⚠️ Manual | ⚠️ Manual |
| Streaming (`yield`) | ✅ | ✅ | ✅ |
| Middleware | ✅ | ✅ | ✅ |
| File handling (`FilePart`) | ✅ | ✅ | ✅ |
| Structured data (`DataPart`) | ✅ | ✅ | ✅ |
| Rich outputs (`Artifact`) | ✅ | ✅ | ✅ |
| Task tracking (`TaskContext`) | ✅ | ✅ | ✅ |
| API Key auth | ✅ | ✅ | ✅ |
| Bearer / JWT auth | ✅ | ✅ | ✅ |
| OAuth2 auth | ✅ | ✅ | ✅ |
| Composite auth | ✅ | ✅ | — |
| AgentNetwork + `delegate()` | ✅ | ✅ | ✅ |
| LLM skills (OpenAI) | ✅ | ✅ | ✅ |
| LLM skills (Anthropic) | ✅ | ✅ | ✅ |
| LLM skills (Ollama) | ✅ | ✅ | ✅ |
| LLM skills (AWS Bedrock) | ✅ | ✅ | ✅ |
| MCP client | ✅ | ✅ | — |
| Router (multi-agent) | ✅ | ✅ | ✅ |
| `get_tool_schemas()` | ✅ | ✅ | ✅ |
| Structured errors | ✅ | ✅ | ✅ |
| In-process TestClient | ✅ | ✅ | ✅ |
| CLI tools | ✅ full | ✅ (no create/serve) | — |
| Multi-agent URL discovery (`discover`) | ✅ CLI (explicit URLs) | ✅ CLI (explicit URLs) | — |
| CORS control | ✅ | ✅ | ✅ (Javalin) |
| TaskHandle (remote task tracking) | ✅ | ✅ | ✅ |
| Agent card discovery | ✅ | ✅ | ✅ |
| `get/cancel` remote tasks | ✅ | ✅ | ✅ |
| Client-side SSE streaming | ✅ | ✅ | ✅ |
| Per-task push notifications | ✅ | ✅ | ✅ |

> **Note on v0.3:** a2a-lite 1.0 does not interoperate with A2A 0.3 agents (explicit decision — no compatibility mode). Lite clients detect 0.3 agent cards and fail with a clear error. See [MIGRATION.md](MIGRATION.md).
>
> ¹ **Java REST:** the agent card may list an `HTTP+JSON` interface for protocol parity, but the Javalin adapter only implements JSON-RPC on `POST /` today.
>
> ² **Python gRPC:** opt-in extra (`a2a-lite[grpc]`). `agent.build_grpc_server()` / `agent.run_grpc()` serve A2A over gRPC (standalone; pair with `agent.run()` if you also need HTTP). Not on by default with `agent.run()`.

---

## A2A Protocol Mapping

Everything in A2A Lite maps directly to the underlying protocol — no magic, no lock-in.

| A2A Lite | A2A Protocol |
|----------|--------------|
| `@agent.skill()` | Agent Skill definition |
| `agent.run()` | JSON-RPC server at `POST /` (+ REST in Python/TypeScript) |
| `streaming=True` + `yield` | SSE streaming (`SendStreamingMessage`) |
| `TaskContext.update()` | Task lifecycle states (submitted → working → completed) |
| `FilePart` | A2A File parts |
| `DataPart` | A2A Data parts |
| `Artifact` | A2A Artifacts |
| `APIKeyAuth` / `BearerAuth` / `OAuth2Auth` | A2A Security schemes (`securitySchemes` in the card) |
| `AgentNetwork.call()` | `SendMessage` over HTTP |
| `/.well-known/agent-card.json` | Agent Card |

---

## Examples

### Showcase: Battleship (playable A2A demo)

End-to-end multi-agent demo: real **A2A v1.0** `SendMessage` calls, web UI, no API key.

| Mode | Command | URL |
|------|---------|-----|
| Human vs bot | `python agent.py` | http://localhost:8790/ |
| Bot vs bot (arena) | `python arena.py` | http://localhost:8793/?mode=arena |

```bash
cd examples/python/11_battleship_lite
pip install -e ../../../packages/python   # from a checkout
python agent.py
# or: python arena.py
```

Docs: [`examples/python/11_battleship_lite/README.md`](examples/python/11_battleship_lite/README.md)

### Google SDK vs A2A Lite — side-by-side comparison

The [`examples/`](examples/) directory contains complete, runnable pairs of the same agent written with the official SDK and with A2A Lite (all migrated to A2A v1.0 / SDK 1.x): hello world, calculator, file handling, auth, streaming, LLM integration, human-in-the-loop, persistence, plus the [battleship showcase](examples/python/11_battleship_lite/) above. See [examples/README.md](examples/README.md).

### Python

| Example | What it shows |
|---------|---------------|
| [01_hello_world.py](packages/python/examples/01_hello_world.py) | Simplest agent (8 lines) |
| [02_calculator.py](packages/python/examples/02_calculator.py) | Multiple skills |
| [03_async_agent.py](packages/python/examples/03_async_agent.py) | Async operations |
| [04_multi_agent/](packages/python/examples/04_multi_agent) | Two agents communicating |
| [05_with_llm.py](packages/python/examples/05_with_llm.py) | OpenAI integration |
| [06_pydantic_models.py](packages/python/examples/06_pydantic_models.py) | Auto Pydantic schemas |
| [06_task_handle_discovery.py](packages/python/examples/06_task_handle_discovery.py) | TaskHandle + card discovery |
| [07_middleware.py](packages/python/examples/07_middleware.py) | Middleware pipeline |
| [07_client_streaming.py](packages/python/examples/07_client_streaming.py) | Client-side SSE streaming |
| [08_streaming.py](packages/python/examples/08_streaming.py) | Streaming responses |
| [09_testing.py](packages/python/examples/09_testing.py) | Built-in TestClient |
| [10_file_handling.py](packages/python/examples/10_file_handling.py) | File upload & processing |
| [11_task_tracking.py](packages/python/examples/11_task_tracking.py) | Long-running tasks with progress |
| [12_with_auth.py](packages/python/examples/12_with_auth.py) | Authentication |
| [13_mcp_tools.py](packages/python/examples/13_mcp_tools.py) | MCP server integration |
| [14_multi_agent_network.py](packages/python/examples/14_multi_agent_network.py) | AgentNetwork + delegate() |
| [15_llm_openai.py](packages/python/examples/15_llm_openai.py) | OpenAI LLM skill |
| [16_llm_anthropic.py](packages/python/examples/16_llm_anthropic.py) | Anthropic LLM skill |
| [17_llm_bedrock.py](packages/python/examples/17_llm_bedrock.py) | AWS Bedrock LLM skill |
| [18_per_task_push.py](packages/python/examples/18_per_task_push.py) | Per-task push notifications |
| [19_capability_negotiation.py](packages/python/examples/19_capability_negotiation.py) | Capability negotiation |
| [20_streaming_negotiation.py](packages/python/examples/20_streaming_negotiation.py) | Streaming negotiation |
| [**11_battleship_lite/**](examples/python/11_battleship_lite/) | **Showcase:** playable battleship UI + multi-agent arena (A2A) |

TypeScript and Java have their own example sets: [`packages/typescript/examples/`](packages/typescript/examples/) and [`packages/java/examples/`](packages/java/examples/). The battleship showcase is Python-only (uses a2a-lite over real A2A).

---

## Language-Specific Docs

| Language | Package | README |
|----------|---------|--------|
| Python | [`packages/python`](packages/python) | [packages/python/README.md](packages/python/README.md) |
| TypeScript | [`packages/typescript`](packages/typescript) | [packages/typescript/README.md](packages/typescript/README.md) |
| Java | [`packages/java`](packages/java) | [packages/java/README.md](packages/java/README.md) |

---

## For AI Coding Assistants

See [AGENT.md](AGENT.md) — a concise reference designed for LLMs writing A2A agents.

---

## Contributing

1. Check if the official A2A SDK already supports the feature
2. Design the simplest possible API that a developer can learn in 30 seconds
3. Keep it optional — never break the 8-line hello world
4. Add tests and at least one example
5. Submit a PR

See [ROADMAP.md](ROADMAP.md) for what's coming next.

---

## License

MIT
