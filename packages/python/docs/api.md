# API Reference

## Core

### Agent

::: a2a_lite.Agent

The main class for creating A2A agents.

```python
from a2a_lite import Agent

agent = Agent(
    name="MyAgent",
    description="What the agent does",
    version="1.0.0",            # Optional, default "1.0.0"
    url=None,                   # Optional, auto-detected
    auth=None,                  # Optional AuthProvider
    task_store=None,            # Optional: "memory" or TaskStore
    cors_origins=None,          # Optional: ["*"] for open CORS
    production=False,           # Optional: enable production warnings
    network=None,               # Optional: AgentNetwork for multi-agent
)
```

**Key Methods:**

- `agent.skill(name, description, tags, streaming)` — Decorator to register skills
- `agent.middleware(func)` — Decorator to register middleware
- `agent.add_middleware(func)` — Non-decorator middleware registration
- `agent.add_mcp_server(url)` — Register an MCP server
- `agent.delegate(target, skill, **params)` — Call a remote agent
- `agent.on_error(func)` — Register global error handler
- `agent.on_startup(func)` — Register startup hook
- `agent.on_shutdown(func)` — Register shutdown hook
- `agent.on_complete(func)` — Register completion hook
- `agent.run(host, port, log_level)` — Start the server
- `agent.get_app()` — Get Starlette app without running
- `agent.call_remote(url, message, timeout)` — Call remote A2A agent
- `agent.build_agent_card(host, port)` — Build A2A agent card

### SkillDefinition

::: a2a_lite.SkillDefinition

Metadata for a registered skill. Created automatically by `@agent.skill()`.

## Testing

### AgentTestClient

::: a2a_lite.AgentTestClient

```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)
result = client.call("greet", name="World")
assert result == "Hello, World!"
assert result.data == "Hello, World!"
assert result.text == '"Hello, World!"'
```

### AsyncAgentTestClient

::: a2a_lite.AsyncAgentTestClient

```python
client = AsyncAgentTestClient(agent)
result = await client.call("greet", name="World")
await client.close()
```

### TestResult

::: a2a_lite.TestResult

Provides multiple accessors: `.data`, `.text`, `.json()`, `.raw_response`.

## Middleware

### MiddlewareContext / MiddlewareChain

::: a2a_lite.MiddlewareContext
::: a2a_lite.MiddlewareChain

### Built-in Middleware

- `logging_middleware(logger=None)` — Log skill calls
- `timing_middleware()` — Track execution time
- `retry_middleware(max_retries=3, delay=1.0)` — Retry on failure
- `rate_limit_middleware(requests_per_minute=60)` — Rate limiting

## Parts

### TextPart / FilePart / DataPart / Artifact

::: a2a_lite.TextPart
::: a2a_lite.FilePart
::: a2a_lite.DataPart
::: a2a_lite.Artifact

## Tasks

### TaskContext / TaskState / Task / TaskStore

::: a2a_lite.TaskContext
::: a2a_lite.Task
::: a2a_lite.TaskStore

## Auth

### AuthProvider / AuthResult

::: a2a_lite.auth.AuthProvider
::: a2a_lite.auth.AuthResult

### Providers

- `NoAuth()` — No authentication (default)
- `APIKeyAuth(keys, header, query_param)` — API key validation
- `BearerAuth(validator, header)` — Bearer token validation
- `OAuth2Auth(issuer, audience, jwks_uri, algorithms)` — JWT/OAuth2
- `CompositeAuth(providers)` — Try multiple providers

### require_auth Decorator

```python
@agent.skill("admin")
@require_auth(scopes=["admin"])
async def admin_action(data: str, auth: AuthResult) -> str:
    return f"Admin {auth.user_id} performed action"
```

## Errors

### A2ALiteError / SkillNotFoundError / ParamValidationError / AuthRequiredError

::: a2a_lite.errors.A2ALiteError
::: a2a_lite.errors.SkillNotFoundError
::: a2a_lite.errors.ParamValidationError
::: a2a_lite.errors.AuthRequiredError

## Orchestration

### AgentNetwork

::: a2a_lite.orchestration.AgentNetwork

## MCP

### MCPClient

::: a2a_lite.mcp.MCPClient
