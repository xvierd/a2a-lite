# A2A Lite

**Build A2A agents in 8 lines. Add enterprise features when you need them.**

A2A Lite is a simplified wrapper around Google's [A2A Protocol](https://github.com/google/a2a) SDK. It lets you build interoperable AI agents with minimal boilerplate, then progressively add features like authentication, streaming, middleware, MCP tools, and multi-agent orchestration.

## Quick Start

### Installation

```bash
pip install a2a-lite
```

### Hello World (8 lines)

```python
from a2a_lite import Agent

agent = Agent(name="Bot", description="A simple bot")

@agent.skill("greet")
async def greet(name: str) -> str:
    return f"Hello, {name}!"

agent.run()
```

### Test It (3 lines)

```python
from a2a_lite import AgentTestClient

client = AgentTestClient(agent)
assert client.call("greet", name="World") == "Hello, World!"
```

### Call It

```bash
# Using the CLI (see CLI Reference for all commands)
a2a-lite doctor http://localhost:8787
a2a-lite inspect http://localhost:8787
a2a-lite test http://localhost:8787 greet -p name=World

# Using curl (A2A v1.0 wire)
curl -sS -X POST http://localhost:8787 \
  -H "Content-Type: application/json" \
  -H "A2A-Version: 1.0" \
  -d '{"jsonrpc":"2.0","method":"SendMessage","id":"1",
       "params":{"message":{"role":"ROLE_USER","messageId":"msg1",
       "parts":[{"text":"{\"skill\":\"greet\",\"params\":{\"name\":\"World\"}}"}]}}}'
```
## Features

| Feature | Opt-in? | Extra Dep? |
|---------|---------|------------|
| Skills & Agent Card | Default | No |
| Pydantic validation | Type hints | No |
| Streaming | `streaming=True` | No |
| Middleware | `@agent.middleware` | No |
| Testing | `AgentTestClient` | No |
| Authentication | `auth=` param | No (OAuth needs `[oauth]`) |
| Task tracking | `task_store="memory"` | No |
| File/Data parts | Type hints | No |
| MCP tools | `add_mcp_server()` | `[mcp]` |
| Multi-agent | `AgentNetwork` | No |
| LLM decorators | `@openai_skill` | `[openai]` or `[anthropic]` |

## Optional Extras

```bash
pip install a2a-lite[mcp]        # MCP tool integration
pip install a2a-lite[openai]     # OpenAI skill decorator
pip install a2a-lite[anthropic]  # Anthropic skill decorator
pip install a2a-lite[oauth]      # OAuth2/JWT authentication
pip install a2a-lite[docs]       # Documentation generation
```

## Next Steps

- [Progressive Levels](progressive-levels.md) - Learn features step by step
- [CLI Reference](cli.md) - Command-line tools
- [API Reference](api.md) - Full API docs
- [Examples](examples.md) - Working code examples
