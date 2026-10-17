# Migrating to a2a-lite 1.1.0 (A2A Protocol v1.0)

## 1.0.x → 1.1.0

Basic skill registration remains unchanged. This release updates the official SDKs and tightens authentication, callback delivery and task handling:

- **Protocol authentication:** configured authentication now protects task and push operations as well as skill execution. HTTP requests without valid credentials return 401. Tokens and custom providers must identify a nonempty user; OAuth2 tokens without a usable subject/identity are rejected. An explicit `NoAuth` agent still exposes public messaging and tasks.
- **Per-task push:** configure authentication, use a real SDK task ID, and register callbacks through A2A operations or the authenticated client helpers. Callback URLs must use HTTPS, resolve only to public addresses, and contain no URL credentials or fragments. Redirects and environment proxies are disabled, and connections use validated DNS addresses while preserving TLS identity. Private/loopback destinations are no longer accepted.
- **Push storage and payloads:** SDK stores isolate configurations by task, owner and configuration ID. The old standalone `TaskPushRegistry` remains a deprecated local utility and no longer configures network delivery. Python `Agent.push_registry` exposes the SDK async store. Protocol callbacks now carry A2A event payloads and `X-A2A-Notification-Token`, rather than the old custom completion payload; explicitly configured completion notifiers are separate.
- **Task handles:** a peer must return a real `Task` with an ID. Requesting a task handle for a message-only response raises an error instead of inventing an unusable ID.
- **Java standalone:** Javalin now delegates streaming, task operations and push configuration to the official SDK. Clients must send `A2A-Version: 1.0`; JSON-RPC IDs retain their original types. `OAuth2Auth` now verifies JWT signatures against the configured JWKS with Nimbus, checks issuer/audience/expiry/not-before and requires a string subject. Unsigned or forged JWTs are rejected. Tokens without a scope claim grant no scopes.
- **Lifecycle and REST:** Python closes SDK resources on HTTP and gRPC shutdown and uses `application/a2a+json` for REST success and error responses. TypeScript selects a compatible JSON-RPC interface from the agent card and carries authenticated identity into SDK task operations.

Callbacks that previously relied on an invented task ID, anonymous registration or a private URL must migrate before upgrading. Custom protocol stores must implement the SDK ownership/scoping contract; the default stores provide it automatically.

## Earlier 0.3 → 1.0 migration

a2a-lite 1.0.0 introduced the migration of all three packages (Python, TypeScript, Java) from A2A protocol **0.3** to **A2A protocol v1.0**. Version 1.1.0 uses the following official SDK baseline, checked on **2026-10-17**.

| Package | Version | Underlying SDK |
|---|---|---|
| `a2a-lite` (PyPI) | 1.1.0 | `a2a-sdk[http-server] >= 1.2.2` |
| `a2a-lite` (npm) | 1.1.0 | `@a2a-js/sdk 1.3.0` (Node >= 20) |
| `io.github.xvierd:a2a-lite` (Maven) | 1.1.0 | `org.a2aproject.sdk:a2a-java-sdk-server-common:1.4.0.Final` |

The latest stable specification is [A2A 1.0.1](https://github.com/a2aproject/A2A/releases/tag/v1.0.1). Protocol identifiers use only major and minor versions, so the `A2A-Version` header and agent cards remain **`1.0`**. SDK versions are independent: [Python 1.2.2](https://github.com/a2aproject/a2a-python/releases/tag/v1.2.2), [TypeScript 1.3.0](https://github.com/a2aproject/a2a-js/releases/tag/v1.3.0), and [Java 1.4.0.Final](https://github.com/a2aproject/a2a-java/releases/tag/v1.4.0.Final).

**Java SDK integrations:** since SDK 1.3, Quarkus task operations require a `TaskAuthorizationProvider`. Configure one when using `agent.getExecutor()` with the official server; see the [authorization migration notes](https://a2aproject.github.io/a2a-java/posts/a2a-java-sdk-1-3-0-final-released/#2-fail-closed-authorization-default). Standalone `agent.run()` wires authorization from A2A Lite's `AuthProvider` automatically.

## Basic API retained from 0.3

Basic agent construction and skill registration remain familiar. Apply the 1.1.0 security and task-handle requirements above as well as the protocol changes below:

- The 8-line agent: `Agent(...)` / `new Agent(...)` / `Agent.builder()`, `@agent.skill` / `agent.skill(...)`, and `agent.run()` work exactly as before.
- `AgentTestClient`, `AgentNetwork` + `delegate()`, `TaskHandle`, middleware, lifecycle hooks.
- Auth providers (`APIKeyAuth`, `BearerAuth`, `OAuth2Auth`).
- LLM skills, MCP client, Router, streaming (`yield` / `async function*` / `SkillConfig.withStreaming()`).

Applications using authentication, task handles or callbacks must review the 1.1.0 migration requirements even without direct SDK imports.

## Breaking changes

1. **The served protocol is A2A v1.0.** a2a-lite 1.0 agents cannot talk to 0.3 agents and vice versa. v0.3 is **not** supported (explicit decision — no compatibility mode). Lite clients detect a 0.3 agent card (root-level `url` + `protocolVersion`, no `supportedInterfaces`) and fail with a clear error telling you the peer speaks 0.3.
2. **Well-known path moved.** The agent card is now served at `GET /.well-known/agent-card.json`. The old `/.well-known/agent.json` is no longer served.
3. **AgentCard shape changed.** The served card now has `supportedInterfaces` (list of `{url, protocolBinding, protocolVersion}`) and **no root-level `url` or `protocolVersion`**. If you parsed the card manually, read `supportedInterfaces[0].url` instead.
4. **Python:** requires `a2a-sdk >= 1.2.2` (pulled in automatically by `pip install -U a2a-lite`).
5. **TypeScript:** requires **Node.js >= 20**.
6. **Java:** Maven coordinates changed to **`io.github.xvierd:a2a-lite:1.1.0`** (was `com.a2alite:a2a-lite:0.3.x`). The `com.a2alite.tasks` package was removed — task types (`TaskContext`, `TaskState`, `TaskHandle`, ...) now live directly under `com.a2alite.*`.
7. **Parts on the wire:** v1.0 parts have **no `kind`/`type` discriminator** — a text part is just `{"text": "..."}`. This only affects you if you were parsing raw JSON payloads.
8. **`AgentTestClient` (Python) now accepts `headers=`** — optional HTTP headers sent with every request (e.g. auth headers). New parameter, not breaking.

## SDK 0.3 → 1.x equivalence table

Only relevant if you used types or helpers from the official SDKs directly (e.g. in a custom executor or a hybrid agent).

### Python (`a2a-sdk` 0.3.x → 1.2.2)

| 0.3 | 1.x |
|---|---|
| `A2AStarletteApplication` (removed) | Route factories: `create_agent_card_routes(card)`, `create_jsonrpc_routes(handler, rpc_url)`, `create_rest_routes(handler)` from `a2a.server.routes` |
| `a2a.utils.new_agent_text_message` (removed) | `a2a.helpers.new_text_message` (plus `new_text_part`, `get_message_text`, `new_task_from_user_message`, ...) |
| Pydantic types in `a2a.types` | Protobuf types in `a2a.types` — snake_case kwargs, `HasField()` for oneofs |
| `Role.user` / `TaskState.working` | `Role.ROLE_USER` / `TaskState.TASK_STATE_WORKING` |
| `A2AClient` | Hand-rolled client or `create_client` |
| `message/send`, `message/stream`, `tasks/get`, `tasks/cancel` | `SendMessage`, `SendStreamingMessage`, `GetTask`, `CancelTask` |
| `/.well-known/agent.json` | `/.well-known/agent-card.json` |
| Part `{"kind": "text", "text": ...}` | Part `{"text": ...}` (no discriminator) |
| `DefaultRequestHandler(executor, task_store)` | `DefaultRequestHandler(executor, task_store, agent_card)` — `agent_card` is now required |

### TypeScript (`@a2a-js/sdk` 0.3.x → 1.3.0)

| 0.3 | 1.x |
|---|---|
| `A2AExpressApp` | Express handlers from `@a2a-js/sdk/server/express`: `jsonRpcHandler({requestHandler, userBuilder})`, `restHandler(...)`, `agentCardHandler(...)` |
| `AgentCard` with root `url` / `protocolVersion` | `AgentCard` with `supportedInterfaces: AgentInterface[]` |
| String enums for `TaskState` / `Role` | Numeric enums + `taskStateToJSON()` / `roleToJSON()` |
| `message/send`, `tasks/get`, ... | `SendMessage`, `GetTask`, ... |
| — | Constants: `A2A_PROTOCOL_VERSION`, `A2A_VERSION_HEADER`, `AGENT_CARD_PATH` |
| — | Card signing: `generateAgentCardSignature`, `verifyAgentCardSignature` (also wrapped by a2a-lite as `signAgentCard` / `verifyAgentCard`) |

### Java (`io.github.a2asdk` → `org.a2aproject.sdk` 1.4.0.Final)

| 0.3 | 1.x |
|---|---|
| Maven group `io.github.a2asdk` | `org.a2aproject.sdk` (e.g. `a2a-java-sdk-server-common:1.4.0.Final`, BOM `a2a-java-sdk-bom`) |
| `EventQueue` + `TaskUpdater` in the executor | `AgentEmitter` — `execute(RequestContext, AgentEmitter)` with `startWork()`, `updateStatus(...)`, `complete()`, `fail()`, ... |
| Mutable spec classes | Records in `org.a2aproject.sdk.spec` (`AgentCard` + `AgentCard.Builder`, `AgentInterface`, `TextPart`, ...) |
| `message/send`, `tasks/get`, ... | `SendMessage`, `GetTask`, ... (see `A2AMethods` constants) |

## Migration steps

### Python

```bash
pip install -U a2a-lite        # pulls a2a-sdk[http-server]>=1.2.2
# or
uv add a2a-lite@latest
```

Basic skills retain their registration API. If you pin `a2a-sdk` yourself, bump it to `>=1.2.2`; apply the 1.1.0 authentication, callback and TaskHandle requirements above.

### TypeScript

```bash
npm install a2a-lite@latest    # requires Node.js >= 20
```

No code changes needed for lite-API agents.

### Java

Update the coordinates in your build file:

```groovy
dependencies {
    implementation 'io.github.xvierd:a2a-lite:1.1.0'
    implementation 'io.javalin:javalin:5.6.3'   // HTTP server (standalone mode)
}
```

```xml
<dependency>
    <groupId>io.github.xvierd</groupId>
    <artifactId>a2a-lite</artifactId>
    <version>1.0.1</version>
</dependency>
```

Then fix imports if you used `com.a2alite.tasks.*` — those classes moved to `com.a2alite.*` (e.g. `com.a2alite.TaskContext`).

## New in 1.0.0 worth trying

- **REST (HTTP+JSON) transport** out of the box in Python and TypeScript (alongside JSON-RPC). Java: planned.
- **`securitySchemes` in the served agent card** (all three) when an auth provider is configured.
- **Signed Agent Cards** (TypeScript, experimental): `signAgentCard` / `verifyAgentCard` exported from `a2a-lite`.
- **`headers=` on Python `AgentTestClient`** for testing authenticated agents.
- Per-task push notifications now use the v1.0 `TaskPushNotificationConfig` methods (`CreateTaskPushNotificationConfig` / `Get` / `Delete`) in all three languages.
