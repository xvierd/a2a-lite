# A2A Lite Roadmap

## ✅ Implemented

### Core Features
- [x] Decorator-based skills (`@agent.skill()`)
- [x] Auto JSON schemas from type hints
- [x] Pydantic model auto-conversion
- [x] Streaming responses (`yield`)
- [x] Middleware system
- [x] Webhooks on completion
- [x] TestClient for easy testing
- [x] CLI tools (init, inspect, test, discover)
- [x] mDNS local discovery

### Enterprise Features (All Optional)
- [x] **Human-in-the-Loop** - `InteractionContext` with `ask()`, `confirm()`, `choose()`
- [x] **File Handling** - `FilePart`, `DataPart`, `Artifact`
- [x] **Task Lifecycle** - `TaskContext` with progress updates
- [x] **Authentication** - `APIKeyAuth`, `BearerAuth`, `OAuth2Auth`
- [x] **Conversation Memory** - `ConversationMemory`

---

## 🚧 Coming Next

### Agent Composition
Mount multiple agents under one server:
```python
from a2a_lite import Router

router = Router()
router.mount("/math", calculator_agent)
router.mount("/search", search_agent)
router.run(port=8787)
```

### LLM Tool Schemas
Auto-generate OpenAI/Anthropic tool format:
```python
@agent.tool
async def get_weather(city: str) -> dict:
    """Get weather for a city."""
    ...

tools = agent.get_tool_schemas()  # Ready for LLM
```

### Background Tasks
Return immediately, process async:
```python
@agent.skill("process", background=True)
async def process(file_url: str) -> str:
    # Returns task_id immediately
    # Client polls for completion
    ...
```

### Observability
Built-in tracing and metrics:
```python
agent = Agent(
    name="Bot",
    tracing="otlp://localhost:4317",
    metrics=True,  # Prometheus at /metrics
)
```

---

## 📋 Future Ideas

### Agent Registry
Discover and call agents from a registry:
```python
from a2a_lite import Registry

registry = Registry("https://registry.example.com")
agent = await registry.get("weather-agent")
```

### Auto Documentation
Serve interactive docs:
```python
agent.run(port=8787, docs=True)  # Docs at /docs
```

### CLI Enhancements
```bash
a2a-lite dev agent.py        # Watch mode
a2a-lite codegen http://...  # Generate client SDK
a2a-lite ping http://...     # Health check
```

### Templates
```bash
a2a-lite init my-agent --template llm
a2a-lite init my-agent --template multi-agent
```

---

## Design Principles

1. **Simple by default** - Hello world in 8 lines
2. **Opt-in complexity** - Add features only when needed
3. **100% A2A compatible** - Always wraps official SDK
4. **Type-safe** - Leverage Python type hints
5. **Test-friendly** - Built-in TestClient

---

## Contributing

1. Check if A2A SDK supports the feature
2. Design the simplest possible API
3. Keep it optional (don't break simple cases)
4. Add examples and tests
5. Submit PR
