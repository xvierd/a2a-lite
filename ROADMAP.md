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
- [x] Multi-agent discovery from explicit URLs (CLI)

### Enterprise Features (All Optional)
- [x] **Human-in-the-Loop** - `InteractionContext` with `ask()`, `confirm()`, `choose()`
- [x] **File Handling** - `FilePart`, `DataPart`, `Artifact`
- [x] **Task Lifecycle** - `TaskContext` with progress updates
- [x] **Authentication** - `APIKeyAuth`, `BearerAuth`, `OAuth2Auth`
- [x] **Conversation Memory** - `ConversationMemory`

---

## ✅ Recently Shipped

- [x] **A2A protocol v1.0 migration** — all three packages use the official 1.x SDKs (introduced in a2a-lite 1.0.0; current SDK baseline below).
- [x] **v1.0 wire format and discovery** — `SendMessage`, `A2A-Version` header, new AgentCard shape (`supportedInterfaces`), card at `/.well-known/agent-card.json` (all languages). All three standalone servers serve `SendStreamingMessage`/`GetTask`/`CancelTask`.
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
- [x] **OAuth2Auth** — JWT signature and claim validation (Python, TypeScript, Java)
- [x] **MCP client** — connect to Model Context Protocol servers (Python, TypeScript)
- [x] **Structured error types** — `SkillNotFoundError`, `ParamValidationError`, etc. (all languages)
- [x] **Multi-modal parts** — `FilePart`, `DataPart`, `Artifact` (all languages)
- [x] **Task tracking** — `TaskContext` with progress updates (all languages)
- [x] **CLI tools** — `init`, `inspect`, `test`, `discover` (Python, TypeScript)

---

## SDK maintenance review — 2026-10-17

The 1.1.0 maintenance release updates the SDK baseline and addresses the six audit follow-ups below.

| Component | Previous SDK baseline | Updated stable baseline |
|---|---|---|
| Python | 1.1.2 | [1.2.2](https://github.com/a2aproject/a2a-python/releases/tag/v1.2.2) |
| TypeScript | 1.0.1 | [1.3.0](https://github.com/a2aproject/a2a-js/releases/tag/v1.3.0) |
| Java | 1.1.0.Final | [1.4.0.Final](https://github.com/a2aproject/a2a-java/releases/tag/v1.4.0.Final) |

The latest stable [specification is 1.0.1](https://github.com/a2aproject/A2A/releases/tag/v1.0.1). Its patch number does not change wire compatibility: agent cards and `A2A-Version` keep `1.0`.

### Implemented in 1.1.0

- All three packages route push configuration through official SDK task handlers, enforce authenticated ownership and configuration IDs, and restrict callbacks to public HTTPS destinations. Delivery pins validated DNS answers, preserves TLS verification, disables redirects/proxies and bounds resource use.
- Java standalone uses the official SDK for SSE and task lifecycle, preserves JSON-RPC IDs, validates protocol versions, and propagates authenticated ownership. OAuth2 always verifies signatures through Nimbus and validates issuer, audience, expiry and subject.
- TypeScript selects a compatible JSON-RPC interface during discovery, propagates authenticated principals, applies CORS before authentication and accepts REST A2A media types.
- Python closes SDK work on HTTP and gRPC shutdown and normalizes REST error media types. Callback errors and authentication failures avoid disclosing secrets.
- All TaskHandle clients require a real task ID rather than inventing one for message-only responses.
- Prepared CI/release workflow improvements build distributions, check the persistence example, validate tag/package versions and signing prerequisites, and default to unpublished dry runs. Their delivery is pending GitHub workflow permission; see `tasks/todo.md`.

### Verification and publication

Local verification: **1,205 tests passed** — Python 643 (one optional Docker test skipped, 91.33% coverage), TypeScript 339 (84.83% line coverage) and Java 223. Full lint/format/type checks, Python wheel/sdist, TypeScript ESM/CJS/declarations, Java example compilation and all eight Java example builds passed. TypeScript retains 16 existing lint warnings. Authenticated Python↔TypeScript calls, SSE, discovery and 401 rejection passed against temporary live servers. Independent review covered authentication and callback delivery. GitHub CI and publication status are tracked in [`tasks/todo.md`](tasks/todo.md).

Java publication requires Maven Central token credentials and a valid GPG private key. The earlier [Maven publication](https://github.com/xvierd/a2a-lite/actions/runs/31280734960) failed to read its signing key; the prepared workflow checks this explicitly and supports an unsigned artifact dry run once GitHub workflow permission is enabled. See [release instructions](.github/RELEASING.md).

## 🚧 Coming Next

### gRPC Transport
Third A2A v1.0 binding alongside JSON-RPC and REST.
- **Python:** experimental today (`a2a-lite[grpc]`, `agent.run_grpc()` / `build_grpc_server()`).
- **TypeScript / Java:** still planned.

### ListTasks
Provide a uniform Lite client helper for v1.0 `ListTasks` discovery and history across all languages. Java standalone now exposes the SDK protocol operation.

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
3. **A2A interoperability** - Use official SDKs and document the supported features of each transport
4. **Type-safe** - Leverage Python type hints
5. **Test-friendly** - Built-in TestClient

---

## Contributing

1. Check if A2A SDK supports the feature
2. Design the simplest possible API
3. Keep it optional (don't break simple cases)
4. Add examples and tests
5. Submit PR
