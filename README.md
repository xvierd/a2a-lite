<p align="center">
  <h1 align="center">A2A Lite</h1>
  <p align="center">
    <strong>The simplest way to build agents for Google's A2A Protocol.</strong>
  </p>
  <p align="center">
    <a href="https://pypi.org/project/a2a-lite/"><img src="https://img.shields.io/pypi/v/a2a-lite?label=PyPI&logo=pypi&logoColor=white" alt="PyPI"></a>
    <a href="https://pypi.org/project/a2a-lite/"><img src="https://img.shields.io/pypi/pyversions/a2a-lite?logo=python&logoColor=white" alt="Python"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  </p>
  <p align="center">
    <a href="#installation">Installation</a> &bull;
    <a href="#quick-start">Quick Start</a> &bull;
    <a href="#progressive-complexity">Features</a> &bull;
    <a href="#examples-python">Examples</a> &bull;
    <a href="https://pypi.org/project/a2a-lite/">PyPI</a> &bull;
    <a href="ROADMAP.md">Roadmap</a>
  </p>
</p>

---

A2A Lite wraps the official A2A SDKs ([Python](https://github.com/a2aproject/a2a-python), [TypeScript](https://github.com/a2aproject/a2a-js), [Java](https://github.com/a2aproject/a2a-java)) to give you a simple, decorator-based API that stays **100% protocol-compatible**.

## Why A2A Lite?

|  | Official A2A SDK | A2A Lite |
|---|---|---|
| Hello World | ~80 lines, 3 files | **8 lines, 1 file** |
| JSON schemas | Manual | **Auto-generated from types** |
| Learning curve | Steep | **Progressive** |
| CLI tools | — | **init, inspect, test, discover** |
| Testing | Manual setup | **Built-in TestClient** |

## Quick Start

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
    name="Bot",
    description="My bot"
)

@agent.skill("greet")
async def greet(name: str):
    return f"Hello, {name}!"

agent.run()
```

</td>
<td>

```typescript
import { Agent } from 'a2a-lite';

const agent = new Agent({
  name: 'Bot',
  description: 'My bot'
});

agent.skill('greet', async ({ name }) =>
  `Hello, ${name}!`
);

agent.run();
```

</td>
<td>

```java
var agent = Agent.builder()
    .name("Bot")
    .description("My bot")
    .build();

agent.skill("greet", params ->
    "Hello, " + params.get("name") + "!"
);

agent.run();
```

</td>
</tr>
</table>

That's it. A fully compliant A2A agent, discoverable by any A2A client.

## Installation

### Python
```bash
pip install a2a-lite
# or
uv add a2a-lite
```

### TypeScript
```bash
npm install a2a-lite
```

### Java (Gradle)
```groovy
dependencies {
    implementation 'com.a2alite:a2a-lite:0.2.5'
    implementation 'io.javalin:javalin:5.6.3'
}
```

---

## Progressive Complexity

A2A Lite follows a *use only what you need* philosophy. Start with a basic skill and add capabilities as your agent grows.

### Level 1 — Just Works

```python
from a2a_lite import Agent

agent = Agent(name="Bot", description="A bot")

@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

agent.run()
```

### Level 2 — Pydantic Models

Input/output schemas are generated automatically from your type hints.

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

@agent.skill("create_user")
async def create_user(user: User) -> dict:
    return {"id": 1, "name": user.name}
```

### Level 3 — Streaming

Just `yield` instead of `return`.

```python
@agent.skill("chat", streaming=True)
async def chat(message: str):
    for word in message.split():
        yield word + " "
```

### Level 4 — Middleware

Cross-cutting concerns (logging, metrics, rate-limiting) without touching skill code.

```python
@agent.middleware
async def log_requests(ctx, next):
    print(f"Calling: {ctx.skill}")
    return await next()
```

### Level 5 — File Handling

Accept and return files through the A2A protocol.

```python
from a2a_lite import FilePart

@agent.skill("summarize")
async def summarize(doc: FilePart) -> str:
    content = await doc.read_text()
    return f"Summary: {content[:100]}..."
```

### Level 6 — Task Tracking

Long-running operations with progress updates.

```python
from a2a_lite import TaskContext

agent = Agent(name="Bot", description="A bot", task_store="memory")

@agent.skill("process")
async def process(data: str, task: TaskContext) -> str:
    await task.update("working", "Starting...", progress=0.0)
    for i in range(10):
        await task.update("working", f"Step {i}/10", progress=i/10)
    return "Done!"
```

### Level 7 — Authentication

API key, Bearer/JWT, and OAuth2 — all optional, all hashed in memory with SHA-256.

```python
from a2a_lite import Agent, APIKeyAuth

agent = Agent(
    name="SecureBot",
    description="A secure bot",
    auth=APIKeyAuth(keys=["secret-key"]),
)
```

### Level 8 — Production Mode

CORS control and production safety checks.

```python
agent = Agent(
    name="Bot",
    description="A bot",
    cors_origins=["https://myapp.com"],
    production=True,
)
```

---

## Testing

Every language ships a `TestClient` so you can test without HTTP.

<table>
<tr>
<th>Python</th>
<th>TypeScript</th>
<th>Java</th>
</tr>
<tr>
<td>

```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)
result = client.call("greet", name="World")
assert result == "Hello, World!"
```

</td>
<td>

```typescript
import { AgentTestClient } from 'a2a-lite';

const client = new AgentTestClient(agent);
const result = await client.call('greet', { name: 'World' });
expect(result).toBe('Hello, World!');
```

</td>
<td>

```java
var client = new AgentTestClient(agent);
assertThat(client.call("greet", Map.of("name", "World")))
    .isEqualTo("Hello, World!");
```

</td>
</tr>
</table>

---

## CLI (Python)

```bash
a2a-lite init my-agent          # Scaffold a new project
a2a-lite serve agent.py         # Run an agent from file
a2a-lite inspect http://...     # View agent card & skills
a2a-lite test http://... skill  # Smoke-test a skill
a2a-lite discover               # Find agents on the local network (mDNS)
```

---

## Feature Matrix

| Feature | Python | TypeScript | Java |
|---------|--------|------------|------|
| Basic skills | `@agent.skill()` | `agent.skill()` | `agent.skill()` |
| Pydantic / Zod / POJO | Auto | Manual | Manual |
| Streaming | `yield` | `yield` | — |
| Middleware | `@agent.middleware` | `agent.use()` | `agent.use()` |
| File handling | `FilePart` | `FilePart` | — |
| Structured data | `DataPart` | `DataPart` | — |
| Rich outputs | `Artifact` | `Artifact` | — |
| Task tracking | `TaskContext` | — | — |
| API Key auth | `APIKeyAuth` | `APIKeyAuth` | `APIKeyAuth` |
| Bearer / JWT | `BearerAuth` | `BearerAuth` | `BearerAuth` |
| OAuth2 | `OAuth2Auth` | — | — |
| CORS | `cors_origins=[...]` | `corsOrigins` | — |
| Testing | `AgentTestClient` | `AgentTestClient` | `AgentTestClient` |
| CLI | `a2a-lite` | — | — |
| mDNS discovery | `a2a-lite discover` | — | — |

---

## A2A Protocol Mapping

Everything in A2A Lite maps directly to the underlying protocol — no magic, no lock-in.

| A2A Lite | A2A Protocol |
|----------|--------------|
| `@agent.skill()` / `agent.skill()` | Agent Skills |
| `streaming=True` | SSE Streaming |
| `TaskContext.update()` | Task lifecycle states |
| `FilePart` | A2A File parts |
| `DataPart` | A2A Data parts |
| `Artifact` | A2A Artifacts |
| `APIKeyAuth` / `BearerAuth` | Security schemes |

---

## Examples (Python)

| Example | What it shows |
|---------|---------------|
| [01_hello_world.py](packages/python/examples/01_hello_world.py) | Simplest agent (8 lines) |
| [02_calculator.py](packages/python/examples/02_calculator.py) | Multiple skills |
| [03_async_agent.py](packages/python/examples/03_async_agent.py) | Async operations & lifecycle hooks |
| [04_multi_agent/](packages/python/examples/04_multi_agent) | Two agents communicating |
| [05_with_llm.py](packages/python/examples/05_with_llm.py) | OpenAI / Anthropic integration |
| [06_pydantic_models.py](packages/python/examples/06_pydantic_models.py) | Auto Pydantic conversion |
| [07_middleware.py](packages/python/examples/07_middleware.py) | Middleware pipeline |
| [08_streaming.py](packages/python/examples/08_streaming.py) | Streaming responses |
| [09_testing.py](packages/python/examples/09_testing.py) | Built-in TestClient |
| [10_file_handling.py](packages/python/examples/10_file_handling.py) | File upload & processing |
| [11_task_tracking.py](packages/python/examples/11_task_tracking.py) | Progress updates |
| [12_with_auth.py](packages/python/examples/12_with_auth.py) | Authentication |

---

## Language-Specific Docs

| Language | Package | Docs |
|----------|---------|------|
| Python | [`a2a-lite`](packages/python) | [packages/python/README.md](packages/python/README.md) |
| TypeScript | [`a2a-lite`](packages/typescript) | [packages/typescript/README.md](packages/typescript/README.md) |
| Java | [`a2a-lite`](packages/java) | [packages/java/README.md](packages/java/README.md) |

---

## For AI Coding Assistants

See [AGENT.md](AGENT.md) — a concise reference designed for LLMs that are writing A2A agents.

---

## Contributing

1. Check if the official A2A SDK already supports the feature
2. Design the simplest possible API
3. Keep it optional — never break the 8-line hello world
4. Add examples and tests
5. Submit a PR

See [ROADMAP.md](ROADMAP.md) for what's coming next.

---

## License

MIT
