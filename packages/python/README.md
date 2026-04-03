# A2A Lite — Python

[![PyPI](https://img.shields.io/pypi/v/a2a-lite?label=PyPI&logo=pypi&logoColor=white)](https://pypi.org/project/a2a-lite/)
[![GitHub](https://img.shields.io/badge/GitHub-a2a--lite-blue?logo=github)](https://github.com/xvierd/a2a-lite)

> **A2A Lite is designed for learning and prototyping.** It's the friendly on-ramp to Google's A2A Protocol — get familiar with agent-to-agent concepts with minimal boilerplate before diving into the full [google/a2a-python](https://github.com/a2aproject/a2a-python) SDK. Perfect for courses, POCs, and demos.

**Build A2A agents in 8 lines. Add features when you need them.**

Wraps the official [A2A Python SDK](https://github.com/a2aproject/a2a-python) with a simple, decorator-based API. 100% protocol-compatible.

```python
from a2a_lite import Agent

agent = Agent(name="Bot", description="My bot")

@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

agent.run()
```

---

## Installation

```bash
pip install a2a-lite
# or
uv add a2a-lite
```

**Requirements:** Python 3.10+

---

## Quick Start

### 1. Create an agent

```python
from a2a_lite import Agent

agent = Agent(name="Calculator", description="Does math")

@agent.skill("add")
async def add(a: int, b: int) -> int:
    return a + b

@agent.skill("multiply")
async def multiply(a: int, b: int) -> int:
    return a * b

agent.run(port=8787)
```

### 2. Test it (no HTTP needed)

```python
from a2a_lite import Agent, AgentTestClient

agent = Agent(name="Calculator", description="Does math")

@agent.skill("add")
async def add(a: int, b: int) -> int:
    return a + b

client = AgentTestClient(agent)
result = client.call("add", a=2, b=3)
assert result == 5
```

### 3. Call it over the network

```bash
curl -X POST http://localhost:8787/ \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "message/send",
    "id": "1",
    "params": {
      "message": {
        "role": "user",
        "parts": [{"type": "text", "text": "{\"skill\": \"add\", \"params\": {\"a\": 2, \"b\": 3}}"}],
        "messageId": "msg-1"
      }
    }
  }'
```

---

## Progressive Complexity

### Level 1 — Basic Skills

```python
from a2a_lite import Agent

agent = Agent(name="Bot", description="A bot")

@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

agent.run()
```

### Level 2 — Pydantic Models

Pass dicts from callers — they're auto-converted to Pydantic models:

```python
from pydantic import BaseModel

class User(BaseModel):
    name: str
    email: str

@agent.skill("create_user")
async def create_user(user: User) -> dict:
    return {"id": 1, "name": user.name}
```

Lists of models work too:

```python
from typing import List

@agent.skill("count_users")
async def count_users(users: List[User]) -> int:
    return len(users)
```

### Level 3 — Streaming

Just `yield` instead of `return`:

```python
@agent.skill("chat", streaming=True)
async def chat(message: str):
    for word in message.split():
        yield word + " "
```

### Level 4 — Middleware

Cross-cutting concerns without touching skill code:

```python
@agent.middleware
async def log_requests(ctx, next):
    print(f"Calling: {ctx.skill}")
    result = await next()
    print(f"Result: {result}")
    return result
```

Built-in middleware:

```python
from a2a_lite import logging_middleware, timing_middleware, retry_middleware, rate_limit_middleware

agent.add_middleware(logging_middleware)
agent.add_middleware(timing_middleware)
agent.add_middleware(rate_limit_middleware(max_per_minute=60))
agent.add_middleware(retry_middleware(max_retries=3))
```

### Level 5 — File Handling

Accept and return files through the A2A protocol:

```python
from a2a_lite import FilePart

@agent.skill("summarize")
async def summarize(doc: FilePart) -> str:
    content = await doc.read_text()
    return f"Summary: {content[:100]}..."
```

### Level 6 — Task Tracking

Long-running operations with progress updates:

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

API keys are hashed in memory using SHA-256 — plaintext keys are never stored.

```python
from a2a_lite import Agent, APIKeyAuth

agent = Agent(
    name="SecureBot",
    description="A secure bot",
    auth=APIKeyAuth(keys=["secret-key-1", "secret-key-2"]),
)
```

Other auth providers:

```python
from a2a_lite.auth import BearerAuth, OAuth2Auth

# Bearer/JWT
agent = Agent(
    name="Bot", description="A bot",
    auth=BearerAuth(secret="your-jwt-secret"),
)

# OAuth2 (requires: pip install a2a-lite[oauth])
agent = Agent(
    name="Bot", description="A bot",
    auth=OAuth2Auth(issuer="https://auth.example.com", audience="my-api"),
)
```

Skills can receive auth results by type-hinting a parameter as `AuthResult`:

```python
from a2a_lite.auth import AuthResult

@agent.skill("whoami")
async def whoami(auth: AuthResult) -> dict:
    return {"user": auth.identity, "scheme": auth.scheme}
```

### Level 8 — CORS & Production Mode

```python
agent = Agent(
    name="Bot",
    description="A bot",
    cors_origins=["https://myapp.com", "https://admin.myapp.com"],
    production=True,  # Warns if running over HTTP
)
```

### Level 10 — Multi-Agent Communication

#### TaskHandle — track remote tasks

```python
from a2a_lite import Agent, AgentNetwork, TaskHandle

network = AgentNetwork()
network.add("data", "http://localhost:8787")

agent = Agent(name="Orchestrator", network=network)

@agent.skill("process")
async def process(query: str) -> str:
    # Get a TaskHandle instead of just the result
    handle = await agent.delegate("data", "fetch", query=query, return_handle=True)
    print(f"Task ID: {handle.task_id}")
    print(f"Agent: {handle.agent_url}")
    print(f"Result: {handle.result}")
    return str(handle.result)
```

#### Task Lifecycle — poll and cancel remote tasks

Use convenience methods directly on the handle, or via the network by name:

```python
# Poll status directly on the handle
status = await handle.get_status()
status = await handle.get_status(timeout=15.0)

# Or poll via network name
status = await network.get_task("data", handle.task_id)
status = await network.get_task("data", handle.task_id, timeout=15.0)

# Cancel directly on the handle
await handle.cancel()
await handle.cancel(timeout=15.0)

# Or cancel via network name
await network.cancel_task("data", handle.task_id)
await network.cancel_task("data", handle.task_id, timeout=15.0)
```

Low-level functions are also available:

```python
from a2a_lite import get_remote_task, cancel_remote_task

status = await get_remote_task("http://localhost:8787", task_id)
await cancel_remote_task("http://localhost:8787", task_id)
```

#### Agent Card Discovery — inspect before calling

```python
from a2a_lite import discover, AgentCardInfo

# Fetch an agent's capabilities before calling
card = await discover("http://localhost:8787")
print(f"Agent: {card.name} v{card.version}")
print(f"Skills: {[s['name'] for s in card.skills]}")
print(f"Streaming: {card.supports_streaming}")

# Auto-discover when registering
network.add("data", "http://localhost:8787", auto_discover=True)

# Validate skill exists before delegating
result = await agent.delegate("data", "fetch", query="hello", discover=True)
```

#### Client-Side SSE Streaming

When calling a remote streaming agent, consume its chunks as they arrive instead of waiting for the full response:

```python
from a2a_lite import Agent, AgentNetwork, stream_remote_skill

# Agent consuming a remote streaming skill
@agent.skill("display")
async def display(topic: str) -> str:
    chunks = []
    async for chunk in agent.delegate("story", "tell_story", topic=topic, stream=True):
        print(chunk, end="", flush=True)
        chunks.append(chunk)
    return "".join(chunks)
```

Or call directly:
```python
from a2a_lite import stream_remote_skill

async for chunk in stream_remote_skill("http://localhost:8787", "tell_story", {"topic": "dragons"}):
    print(chunk, end="", flush=True)
```

### Per-Task Push Notifications

Register a webhook for a specific task — the server calls it when that task completes:

```python
from a2a_lite import set_task_push_notification, delete_task_push_notification

# Get a handle when delegating
handle = await agent.delegate("data", "fetch", query="hello", return_handle=True)

# Register a webhook for this specific task
await handle.subscribe("https://my-app.com/webhook", token="secret")

# Or use the standalone function
await set_task_push_notification(
    "http://localhost:8787", handle.task_id,
    "https://my-app.com/webhook", token="secret"
)

# Retrieve registration
config = await handle.get_push_config()

# Remove registration
await handle.unsubscribe()
```

The server-side `TaskPushRegistry` is automatically created on every Agent. When a task completes, the registered webhook receives:
```json
{"task_id": "...", "skill": "process", "result": ..., "status": "completed", "timestamp": 1234567890}
```

### Level 9 — Lifecycle Hooks

```python
@agent.on_startup
async def startup():
    print("Agent starting...")

@agent.on_shutdown
async def shutdown():
    print("Agent stopping...")

@agent.on_complete
async def notify(skill_name, result, ctx):
    print(f"Skill {skill_name} completed with: {result}")

@agent.on_error
async def handle_error(error: Exception):
    return {"error": str(error), "type": type(error).__name__}
```

---

## Testing

### AgentTestClient

Synchronous test client for pytest:

```python
from a2a_lite import Agent, AgentTestClient

agent = Agent(name="Bot", description="Test")

@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

@agent.skill("info")
async def info(name: str, age: int) -> dict:
    return {"name": name, "age": age}


def test_simple_result():
    client = AgentTestClient(agent)
    result = client.call("greet", name="World")
    assert result == "Hello, World!"


def test_dict_result():
    client = AgentTestClient(agent)
    result = client.call("info", name="Alice", age=30)
    assert result.data["name"] == "Alice"
    assert result.data["age"] == 30


def test_list_skills():
    client = AgentTestClient(agent)
    skills = client.list_skills()
    assert "greet" in skills
    assert "info" in skills
```

### TestResult

Every `client.call()` returns a `TestResult`:

| Property | Description |
|----------|-------------|
| `.data` | Parsed Python object (dict, list, int, str, etc.) |
| `.text` | Raw text string from the response |
| `.json()` | Parse text as JSON (raises on invalid JSON) |
| `.raw_response` | Full A2A response dict |

`TestResult` supports direct equality for simple values (`result == 5`), but use `.data` for subscripting (`result.data["key"]`).

### AsyncAgentTestClient

For async test frameworks:

```python
import pytest
from a2a_lite import AsyncAgentTestClient

@pytest.mark.asyncio
async def test_async():
    client = AsyncAgentTestClient(agent)
    result = await client.call("greet", name="World")
    assert result == "Hello, World!"
    await client.close()
```

### Streaming Tests

```python
def test_streaming():
    client = AgentTestClient(agent)
    results = client.stream("chat", message="hello world")
    assert len(results) == 2
```

---

## CLI

```bash
a2a-lite init my-agent          # Scaffold a new project
a2a-lite serve agent.py         # Run an agent from file
a2a-lite inspect http://...     # View agent card & skills
a2a-lite test http://... skill  # Smoke-test a skill
a2a-lite discover               # Find agents on the local network (mDNS)
a2a-lite info <url>             # Show agent info in compact plain-text format
a2a-lite version                # Show version
```

---

## API Reference

### Agent

```python
Agent(
    name: str,                          # Required
    description: str,                   # Required
    version: str = "1.0.0",
    url: str = None,                    # Override auto-detected URL
    auth: AuthProvider = None,          # Authentication provider
    task_store: str | TaskStore = None, # "memory" or custom TaskStore
    cors_origins: List[str] = None,     # CORS allowed origins
    production: bool = False,           # Enable production warnings
)
```

**Methods:**

| Method | Description |
|--------|-------------|
| `@agent.skill(name, **config)` | Register a skill via decorator |
| `@agent.middleware` | Register middleware via decorator |
| `agent.add_middleware(fn)` | Register middleware function |
| `@agent.on_complete` | Register completion hook |
| `@agent.on_startup` | Register startup hook |
| `@agent.on_shutdown` | Register shutdown hook |
| `@agent.on_error` | Register error handler |
| `agent.run(port=8787)` | Start the server |
| `agent.get_app()` | Get the ASGI app (for custom deployment) |

### Skill Decorator

```python
@agent.skill(
    name: str = None,             # Skill name (defaults to function name)
    description: str = None,      # Human-readable description
    tags: List[str] = None,       # Categorization tags
    streaming: bool = False,      # Enable streaming
)
```

### Auth Providers

| Provider | Usage |
|----------|-------|
| `APIKeyAuth(keys=[...])` | API key auth (keys hashed with SHA-256) |
| `BearerAuth(secret=...)` | JWT/Bearer token auth |
| `OAuth2Auth(issuer=..., audience=...)` | OAuth2 auth (requires `a2a-lite[oauth]`) |
| `NoAuth()` | No auth (default) |

### Special Parameter Types

Auto-injected when detected in skill function signatures:

| Type | Description |
|------|-------------|
| `TaskContext` | Task lifecycle management (requires `task_store`) |
| `AuthResult` | Authentication result injection |
| `FilePart` | File upload handling |
| `DataPart` | Structured data handling |

### Orchestration

| Export | Description |
|--------|-------------|
| `AgentNetwork` | Registry of named remote agents |
| `TaskHandle` | Handle to a remote task with `task_id` and `result` |
| `AgentCardInfo` | Parsed agent card with `name`, `version`, `skills`, `supports_streaming` |
| `discover(url)` | Fetch a remote agent's card from `/.well-known/agent.json` |
| `get_remote_task(url, task_id)` | Poll the status of a remote task |
| `cancel_remote_task(url, task_id)` | Request cancellation of a remote task |
| `stream_remote_skill(url, skill, params)` | Stream SSE chunks from a remote agent skill |

---

## Examples

| Example | What it shows |
|---------|---------------|
| [01_hello_world.py](examples/01_hello_world.py) | Simplest agent (8 lines) |
| [02_calculator.py](examples/02_calculator.py) | Multiple skills |
| [03_async_agent.py](examples/03_async_agent.py) | Async operations & lifecycle hooks |
| [04_multi_agent/](examples/04_multi_agent) | Two agents communicating |
| [05_with_llm.py](examples/05_with_llm.py) | OpenAI / Anthropic integration |
| [06_pydantic_models.py](examples/06_pydantic_models.py) | Auto Pydantic conversion |
| [07_middleware.py](examples/07_middleware.py) | Middleware pipeline |
| [08_streaming.py](examples/08_streaming.py) | Streaming responses |
| [09_testing.py](examples/09_testing.py) | Built-in TestClient |
| [10_file_handling.py](examples/10_file_handling.py) | File upload & processing |
| [11_task_tracking.py](examples/11_task_tracking.py) | Progress updates |
| [12_with_auth.py](examples/12_with_auth.py) | Authentication |

---

## A2A Protocol Mapping

Everything maps directly to the underlying protocol — no magic, no lock-in.

| A2A Lite | A2A Protocol |
|----------|--------------|
| `@agent.skill()` | Agent Skills |
| `streaming=True` | SSE Streaming |
| `TaskContext.update()` | Task lifecycle states |
| `FilePart` | A2A File parts |
| `DataPart` | A2A Data parts |
| `Artifact` | A2A Artifacts |
| `APIKeyAuth` / `BearerAuth` | Security schemes |

---

## License

MIT
