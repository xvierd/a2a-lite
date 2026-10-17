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

### Optional Application Features
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

## Learning-to-production improvement plan — 2026-10-17

**Objective:** preserve the small, infrastructure-free first agent and provide a tested path to operating authenticated, durable agents with explicit capacity and recovery guarantees. The milestones below preserve the approved acceptance criteria. The 1.2.0 implementation now provides progressive examples, managed runtimes and durable reference adapters in all three languages; deployment qualification and external release prerequisites remain separate gates.

The starting baseline was the merged [PR #5](https://github.com/xvierd/a2a-lite/pull/5): 1,205 local tests and seven CI environments passed. Implementation of the plan below was approved on 2026-10-17 and is tracked in [`tasks/todo.md`](tasks/todo.md). Functional coverage does not establish throughput, availability or automatic recovery. Release/workflow dependencies remain explicit in that tracker.

### Implementation status

The language implementations and package tests are complete for 1.2.0. [OPERATIONS.md](OPERATIONS.md) describes exact guarantees, defaults and recovery differences; [tasks/todo.md](tasks/todo.md) records validation and remaining work. Python supports opt-in checkpoint re-execution, TypeScript explicit checkpoint continuation, and Java an application-managed checkpoint primitive. Shared durable state does not imply arbitrary function recovery or exactly-once external effects.

Milestones 1–5 have implementations and automated behavioral tests. Their distributed adapters remain reference implementations. Milestone 0 still requires GitHub workflow access and Java publication credentials. Milestone 6 includes repeatable local gates and runbooks, but production SLO qualification, long-duration failure campaigns and an unfamiliar learner's evaluation remain open. Local load measurements cannot substitute for those acceptance targets.

### Scope and architectural decisions

- Preserve skill registration and keep external infrastructure optional for the learning path. Each production capability must have a runnable example, a failure example and a migration guide.
- Validate declared deployment guarantees at startup in every language: a profile requiring authentication rejects NoAuth; one requiring durability rejects incompatible in-memory stores. Fail before accepting traffic instead of silently downgrading. The explicit learning profile remains supported.
- Use official SDK extension points. Share behavioral contracts and protocol fixtures across languages; do not require different SDKs to share a database schema or run mixed-language replicas behind one agent endpoint.
- Propose PostgreSQL as the first operational reference backend. Keep memory for the quickstart; use SQLite only in a learning adapter where the SDK supports it. Additional databases and cloud-specific deployment templates follow demonstrated demand.
- Distinguish durable task **state**, shared **events**, and recoverable skill **execution**. Persisting a Task or replicating its events does not reconstruct an interrupted function or guarantee a single external side effect.
- Define maturity per language, transport and deployment profile. A capability becomes supported only after its corresponding contract and failure tests pass. Python can establish the first durable reference; TypeScript and Java must pass the same behavioral gates before claiming parity.

### Milestones and acceptance gates

| Milestone | Priority / dependency | Deliverable | Acceptance gate |
|---|---|---|---|
| **0. Close the 1.1.0 baseline** | P0; external publishing prerequisites | Review/integrate PR #5, deliver the prepared workflow changes, publish reproducible packages and verify clean installations. | Registry artifacts match the validated release commit; all three packages can run their quickstart from a clean environment. Java credentials and GitHub workflow access are explicitly resolved before claiming release completion. |
| **1. Learning path and consistent task/identity contracts** | P0; can start while release access is pending | Progressive examples, one visible protocol task ID, stable authenticated identity and header-based client credentials. | A learner runs Message → Task → streaming without an LLM account or database; the task ID inside a skill works remotely; credential rotation preserves ownership; cross-user/tenant access is rejected. |
| **2. Managed runtime, resource limits and diagnostics** | P0; identity contract from 1 | Embeddable start/stop lifecycle, bounded admission, deadlines, shutdown draining, readiness and baseline telemetry. | Two agents coexist without terminating their host; saturation has predictable rejection; SIGTERM drains or explicitly interrupts work within its configured deadline; no silently abandoned tasks. |
| **3. Durable state and authorization** | P1; 1 and lifecycle hooks from 2 | Configurable SDK stores/event mechanisms, PostgreSQL reference, migrations, protected callback secrets, retention and backup/restore. | Restart preserves tasks, owners and callback configurations; concurrent writes are handled explicitly; restoration preserves access control; a storage failure never reports successful persistence. |
| **4. Recoverable callback delivery** | P1; 3 | Persistent event-to-delivery handoff, retry dispatcher, failure queue, controlled replay and receiver deduplication. | Crash tests at every persistence/send/acknowledgment boundary lose no accepted callback event; duplicates are identifiable; deleted subscriptions stop future attempts; retries retain SSRF/TLS protections. |
| **5. Multiple replicas and execution recovery** | P2; 2–3; integrate with 4 | Shared event routing, task execution ownership, remote cancellation and a declared recovery/checkpoint model. | Start on A and read/subscribe/cancel through B; after A dies, recover supported tasks or report an explicit interruption; a stale worker cannot overwrite its successor or repeat a protected effect. |
| **6. Qualify and document production profiles** | P2; relevant earlier gates | Cross-language compatibility, load/failure tests, operational runbooks, release upgrades and a published capability/limit matrix. | Reproducible evidence meets agreed latency/error/recovery targets on a declared workload and hardware profile; unsupported guarantees remain visible. |

Milestones 1–2 can progress in parallel once their shared identity/lifecycle contracts are fixed. Callback recovery and the distributed execution prototype can progress in parallel after durable state is available. Milestone 0's credential blockers do not block local design or implementation.

### 1. Learning and identity work

- Build a progressive example in each language: immediate message, queryable task, streaming/cancellation, authenticated peer calls, then persistence and recovery. Clearly separate local application task storage from protocol task storage. Add shared interoperability scenarios to CI from this milestone onward; milestone 6 completes and qualifies the matrix rather than introducing it for the first time.
- Align Python/TypeScript `TaskContext` with the protocol task where applicable; preserve compatibility through an explicit migration. Define how users request task mode for a normal skill without requiring artificial streaming.
- Add a header/credential-provider path consistently to discovery, calls, streams and task helpers. Avoid teaching query-string credentials; scope credentials to the intended endpoint so discovery cannot forward them to an unrelated origin.
- Specify a stable principal and authorized tenant membership before designing durable keys. Include issuer/subject or an equivalent configured namespace; rotating an API key must not silently orphan tasks. Treat a request's tenant field as input requiring authorization.
- Reuse one authorization/store test suite for Get/List/Cancel/Subscribe, continuation and push CRUD/inline configuration. Test identical subjects in different issuers/tenants and authorization filtering before pagination.

### 2. Runtime and operational bounds

- Keep process signals and process exit in executable entry points. Expose a runtime handle that the embedding application can start, stop and await; close SDK handlers, stores, pools and outbound clients it owns.
- Configure limits for active tasks, queued requests, streams, message/artifact sizes, callback configurations, execution deadlines and retained history. Separate admission and rate quotas from execution pools.
- In Java, preserve separate producer/consumer resources: bounding every SDK pool indiscriminately can deadlock event consumers. Test admission saturation and cancellation while consumers remain responsive.
- Define cancellation cooperation explicitly (for example, cancellation context or AbortSignal). Uncooperative user code needs process/worker isolation for hard execution limits; cancelling a promise or thread request is insufficient.
- Add correlated structured logs, traces and metrics for task latency, active/queued work, admission rejection, callback backlog and storage errors. Redact credentials and avoid task/user IDs as unbounded metric labels. Readiness must reflect storage and draining state.

### 3. Durable reference adapters

- **Python:** evaluate the SDK 1.2.2 `VersionedDatabaseTaskStore` with `DatabaseTaskEventStream`, plus `DatabasePushNotificationConfigStore`. Preserve version checks and atomic state/event persistence; an ordinary legacy TaskStore adapter does not provide these guarantees. Expose their configuration together and close their engines correctly. [Official store](https://github.com/a2aproject/a2a-python/blob/v1.2.2/src/a2a/server/cluster/database_task_store.py), [event stream](https://github.com/a2aproject/a2a-python/blob/v1.2.2/src/a2a/server/cluster/database_event_stream.py).
- **TypeScript:** compose the SDK 1.3.0 database task/push stores with the current callback validation and scope rules. Its basic store interface does not itself provide compare-and-swap, execution leases or a shared outbox transaction; validate those boundaries in a small architectural prototype before implementation. [Official persistent-store support](https://github.com/a2aproject/a2a-js/blob/v1.3.0/README.md).
- **Java:** provide a production reference using the same skills/executor with the official SDK/Quarkus and its storage/authorization extensions. If Javalin exposes injectable SDK components, validate coherent combinations and forbid silently falling back to memory. Evaluate official JPA and queue-replication modules; `MainEventBus` is not a generic broker SPI. Keep the blocking-send race regression during any adapter migration. [Official SDK 1.4 extensions](https://a2aproject.github.io/a2a-java/1_4_0_Final/extras/).
- For every adapter: ship schema migrations, expiry/cleanup, backup/restore and rollback compatibility guidance. Protect persisted callback credentials with an external key configuration and test rotation. A persisted task interrupted by a crash must have a defined reconciliation policy even before automatic execution recovery exists.

### 4. Durable callbacks

Define the acceptance boundary and atomic handoff before adding retries. Python's persisted event stream may supply the source; TypeScript/Java need a verified transaction or durable event-log design. Merely replacing the sender leaves a possible gap after saving task state.

Deliver **at least once**, with a stable event identity and documented receiver deduplication. Include bounded exponential retry with jitter, lease/claim ownership, maximum delivery age, inspectable permanent failures and authorized replay. Preserve event ordering where promised; define whether an already in-flight request can finish after subscription deletion. Revalidate public HTTPS/DNS policy on every attempt and keep callback credentials out of logs and error responses.

### 5. Distributed execution

Start with a two-replica architectural prototype per runtime before adding a supported distributed profile. Evaluate the SDK's event/queue extension points and an existing durable execution runtime where appropriate.

Specify task ownership leases, expiry/fencing, concurrent updates, stream reconnect/replay and remote cancellation. Make recoverable skills opt-in with checkpoints/idempotency contracts. Separate transient worker failure from permanent task failure. Test that a resumed task does not silently duplicate billing, email or other external effects; exactly-once execution is not a blanket promise.

### 6. Evidence required for a production claim

- Run the nine language client/server pairings for the common supported protocol surface, plus official-SDK interoperability. Cover Message versus Task, initial SSE snapshots, failures, cancellation, ownership, media types and configuration IDs. Keep a separate transport capability matrix.
- Define load profiles before setting targets: short I/O skills, long tasks, SSE fan-out and a failing callback receiver. Record hardware, payload sizes, concurrency, throughput, p95/p99 latency, error rate and memory/thread/connection limits. Simulate LLM latency in the baseline; measure real provider limits separately.
- Exercise worker kill, database/network interruption, callback outage, graceful deploy, credential rotation, stale-worker writes and backup restore. Agree recovery-time and acceptable-data-loss targets before qualifying a deployment profile.
- Maintain repeatable dependency/security checks, migration/upgrade tests and release provenance. Publish supported SDK/runtime versions and known limitations. Review changed security boundaries; test count alone is not a security audit or availability guarantee.
- Provide operator procedures for deployment, rollback, failed deliveries, overload, retention and incident diagnosis. Validate the learning exercises with someone unfamiliar with the project.

### Initial implementation backlog

1. Document the progressive Message/Task examples and runtime capability matrix; specify task identity and scoped client authentication.
2. Implement header-based client auth, task-ID consistency and reusable identity/store contract tests.
3. Add managed runtime handles, admission limits, shutdown tests and baseline telemetry.
4. Prototype and implement the Python durable reference; then port the behavior to TypeScript and Java using their SDK-specific adapters.
5. Resolve atomic delivery handoff and implement the durable callback dispatcher.
6. Validate two-replica execution/recovery prototypes before committing to their public configuration API.
7. Complete load/failure/upgrade qualification and the production runbooks.

Each item should be a focused PR with its example, migration notes and acceptance evidence. No calendar estimate or capacity promise is fixed until the adapter prototypes and workload targets are known.

## Deferred protocol features

These remain useful improvements after the reliability milestones, or sooner if required by an identified consumer:

- gRPC wrappers for TypeScript/Java; Python's optional gRPC path remains experimental.
- A uniform Lite `ListTasks` client helper across languages.
- Signed Agent Cards for Python/Java; TypeScript support remains experimental.

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
