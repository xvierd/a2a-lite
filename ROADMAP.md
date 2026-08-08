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

## ✅ Recently Shipped

- [x] **A2A protocol v1.0 parity** — all three packages on the official 1.x SDKs: Python `a2a-sdk 1.1.2`, TypeScript `@a2a-js/sdk 1.0.1`, Java `org.a2aproject.sdk 1.1.0.Final` (a2a-lite 1.0.0)
- [x] **v1.0 wire protocol** — `SendMessage`/`SendStreamingMessage`/`GetTask`/`CancelTask`, `A2A-Version` header, new AgentCard shape (`supportedInterfaces`), card at `/.well-known/agent-card.json` (all languages)
- [x] **REST (HTTP+JSON) transport** — out of the box alongside JSON-RPC (Python, TypeScript)
- [x] **Signed Agent Cards** — `signAgentCard` / `verifyAgentCard` (TypeScript, experimental)
- [x] **`securitySchemes` in the served agent card** — when an auth provider is configured (all languages)
- [x] **Per-task push notifications on v1.0** — `TaskPushNotificationConfig` methods (all languages)
- [x] **Google comparison examples rewritten to SDK 1.x** — [`examples/`](examples/) side-by-side suite (Python, TypeScript, Java)
- [x] **`AgentNetwork.call` skill-param collision** — positional-only routing args (`/`) so skills may use params named `name` / `skill` (Python; TS/Java already use a params map)
- [x] **`a2a-lite create` Docker smoke** — generated `Dockerfile` builds successfully with vendored local source (CLI test skips when Docker is unavailable)
- [x] **Battleship showcase** — [`examples/python/11_battleship_lite/`](examples/python/11_battleship_lite/) human vs agent + agent-vs-agent arena over real A2A
- [x] **AgentNetwork + delegate()** — multi-agent orchestration (Python, TypeScript, Java)
- [x] **LLM skills** — OpenAI, Anthropic, Ollama, AWS Bedrock (Python, TypeScript, Java)
- [x] **Router** — mount multiple agents under one server (Python, TypeScript, Java)
- [x] **get_tool_schemas()** — export skill definitions as LLM tool schemas (Python, TypeScript, Java)
- [x] **OAuth2Auth** — JWT claim validation (Python, TypeScript, Java)
- [x] **MCP client** — connect to Model Context Protocol servers (Python, TypeScript)
- [x] **Structured error types** — `SkillNotFoundError`, `ParamValidationError`, etc. (all languages)
- [x] **Multi-modal parts** — `FilePart`, `DataPart`, `Artifact` (all languages)
- [x] **Task tracking** — `TaskContext` with progress updates (all languages)
- [x] **CLI tools** — `init`, `inspect`, `test`, `discover` (Python, TypeScript)

---

## 🚧 Coming Next

### gRPC Transport
Third A2A v1.0 binding alongside JSON-RPC and REST (all languages).

### ListTasks
Expose the v1.0 `ListTasks` method for task discovery and history (all languages).

### Signed Agent Cards (Python, Java)
Port the TypeScript experimental `signAgentCard` / `verifyAgentCard` support.

### Multi-tenancy
Tenant isolation for shared deployments (all languages).

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
