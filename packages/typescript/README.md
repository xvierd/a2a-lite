# A2A Lite — TypeScript

[![npm](https://img.shields.io/npm/v/a2a-lite?label=npm&logo=npm&logoColor=white)](https://www.npmjs.com/package/a2a-lite)
[![GitHub](https://img.shields.io/badge/GitHub-a2a--lite-blue?logo=github)](https://github.com/xvierd/a2a-lite)

> **A2A Lite is designed for learning and prototyping.** It's the friendly on-ramp to Google's A2A Protocol — get familiar with agent-to-agent concepts with minimal boilerplate before diving into the full [a2aproject/a2a-js](https://github.com/a2aproject/a2a-js) SDK. Perfect for courses, POCs, and demos.

**Build A2A agents in 8 lines. Add features when you need them.**

Wraps the official [@a2a-js/sdk](https://github.com/a2aproject/a2a-js) with a simple API and tested A2A 1.0 JSON-RPC/HTTP+JSON interoperability.

> **v1.2.1 — A2A Protocol v1.0.** Uses the official [`@a2a-js/sdk 1.3.0`](https://github.com/a2aproject/a2a-js/releases/tag/v1.3.0). The latest protocol specification is [v1.0.1](https://github.com/a2aproject/A2A/releases/tag/v1.0.1); the wire version remains `1.0`.
> - **Transports:** JSON-RPC + REST (HTTP+JSON) via `agent.run()`; card at `/.well-known/agent-card.json`.
> - **gRPC:** not implemented in TypeScript yet (Python has experimental `run_grpc`; see root Feature Matrix).
> - Requires **Node.js >= 20**. No v0.3 compatibility.
> - Experimental **signed Agent Cards** via `signAgentCard` / `verifyAgentCard`.
> - See [MIGRATION.md](https://github.com/xvierd/a2a-lite/blob/main/MIGRATION.md).

**1.2.1 documentation patch:** Corrected README examples for skills, authentication, task helpers,
streaming and lifecycle handling, with registry-safe links to the guides. Runtime APIs and
dependency versions remain the same as 1.2.0.

Discovery selects an advertised JSON-RPC interface for A2A `1.0`, including when
REST or gRPC appears first. Agents without a compatible interface are rejected.
`returnHandle` requires a task ID issued by the remote agent; a plain Message
still works with regular calls but cannot be used for task management.

Authenticated requests carry their verified `userId` into both SDK transports.
The default SDK stores isolate tasks and push configurations by user and tenant.
Custom `protocolTaskStore` implementations must preserve that same scope contract.
Authentication providers must return a nonempty identity on successful authentication.

Per-task push configurations now use the official SDK API. They require an authenticated
caller, an existing task owned by that caller, independent configuration IDs and a public **HTTPS**
callback URL. Registration and delivery reject private/reserved addresses; delivery
pins DNS resolution, preserves the original TLS identity and never follows redirects
or uses proxy agents. Notifications use the A2A v1.0 `StreamResponse` body and
`application/a2a+json`; `token` is sent in `X-A2A-Notification-Token`.

`TaskHandle.subscribe`, `getPushConfig` and `unsubscribe` retain their existing
arguments and accept an optional final `configId`; the default is the task ID.
`TaskPushRegistry` remains available as a deprecated standalone utility. Direct
`agent.pushRegistry.set(...)` calls no longer register network callbacks; use the
protocol helpers or inline `configuration.taskPushNotificationConfig` instead.

The operator-configured `WebhookPushNotifier` retains its completion-event payload
and HMAC signing. It accepts public HTTP(S) URLs and shares the same address,
redirect and timeout protections; use HTTPS when sending sensitive data. Private
callback destinations require a separately implemented, trusted `PushNotifier`.

```typescript
import { Agent } from 'a2a-lite';

const agent = new Agent({ name: 'Bot', description: 'My bot' });

agent.skill('greet', async ({ name }) =>
  `Hello, ${name}!`
);

await agent.run();
```

---

## A progressive production path

Start with the runnable [Message → Task → stream → authenticated → durable example](https://github.com/xvierd/a2a-lite/blob/main/examples/typescript/11_production_path/README.md).
It requires no external LLM or callback receiver. Its first four steps run locally without PostgreSQL.

```typescript
import { Agent, TaskContext, callRemoteSkillWithHandle } from 'a2a-lite';

const agent = new Agent({ name: 'Tasks', description: 'One real task ID' });
agent.skill('identify', { task: true, taskContext: true }, async ({ task }) => {
  const context = task as TaskContext;
  await context.update('working', 'Halfway', 0.5);
  return context.taskId;
});
const runtime = await agent.start({ host: '127.0.0.1', port: 0 });
try {
  const task = await callRemoteSkillWithHandle(runtime.url, 'identify', {});
  console.log(task.taskId, task.result, await task.get());
} finally {
  await runtime.stop();
}
```

`task: true` returns an SDK Task for a normal skill. `TaskContext` uses that same ID;
progress and terminal state reach the protocol store. Ordinary skills continue returning
Messages. Cancellation and execution deadlines abort `TaskContext.signal`; handlers must
cooperate with that signal. Timeouts cannot terminate arbitrary JavaScript or undo its side effects.

Await `start()` or `run()` to obtain an `AgentRuntime` with `url`, `stats`, `closed` and idempotent
`stop()`. The library installs no process signal handlers and never calls `process.exit`.
The application owns SIGINT/SIGTERM handling. Shutdown stops admission, aborts active skills,
waits for their terminal state to settle, then closes MCP and persistence resources within
the configured grace period. A shutdown deadline or hook failure rejects `stop()`.

### Verified identity and authenticated clients

```typescript
import { Agent, APIKeyAuth, AgentNetwork } from 'a2a-lite';

const auth = new APIKeyAuth({ identities: {
  'current-key': { userId: 'service', namespace: 'company', authorizedTenants: ['team-a'] },
  'rotated-key': { userId: 'service', namespace: 'company', authorizedTenants: ['team-a'] },
} });
const agent = new Agent({ name: 'Secure', description: 'Stable ownership', profile: 'authenticated', auth });
const network = new AgentNetwork();
network.add('secure', 'https://agent.example', {
  tenant: 'team-a',
  credentialProvider: async () => ({ 'X-API-Key': await readCurrentKey() }),
});
```

`readCurrentKey` is an application credential lookup. `headers` and `credentialProvider`
are supported by discovery, direct calls, streams, `Agent.delegate`, network calls and
TaskHandle helpers. Providers run for every request and receive its AbortSignal. Credentials
are bound to the original origin; discovery cannot forward them elsewhere. Redirects fail.
Set `allowedCredentialOrigins` only for deliberately trusted alternate origins.

AuthResult may include trusted `namespace` and `authorizedTenants`. Missing membership permits
only the empty tenant. NoAuth is limited to that tenant and cannot register callbacks.
OAuth uses its verified configured issuer as namespace. Bearer validators may return a verified
identity object as well as the legacy user-ID string. API-key mappings retain ownership across
key rotation. Legacy user IDs remain unchanged except reserved `a2a:v1:` IDs, which are escaped;
namespaced IDs use the shared collision-safe encoding. Existing storage keys in those two cases
need an explicit migration.

### Profiles, limits and readiness

`learning` is the default. `authenticated` requires verified identities and rejects anonymous
fallbacks. `durable` additionally requires a ready `ProtocolPersistence`; it means durable state,
not automatic recovery of arbitrary execution. Custom auth results still fail closed at request time.

The `limits` object controls concurrent requests/streams, per-principal admission, request and
execution deadlines, body/output/snapshot bytes, event count, memory task count, task history,
callback configuration count and shutdown grace. Defaults include 128 requests, 32 streams,
32 requests/8 streams per principal, 1MiB request/output, 4MiB snapshots, 4096 events per execution,
256 history entries, 10000 memory tasks and 8 callbacks per task. Request/execution deadlines
are 60 seconds and shutdown grace is 5 seconds. Capacity rejection is explicit and retryable.

`/health/live` is a liveness probe. `/health/ready` returns `{ ready: false }` with HTTP 503 during
drain or storage failure. `telemetry(event)` receives aggregate counters and event names, never
headers, tokens, callback URLs, payloads or principal IDs. Optional external telemetry exporters
can consume that callback without affecting request handling.

### PostgreSQL, transactional delivery and replica coordination

```typescript
import { Agent, APIKeyAuth, createPostgresPersistence, migratePostgresRuntime } from 'a2a-lite';

const apiKey = process.env.API_KEY;
if (!apiKey) throw new Error('Set API_KEY to a private application credential');
// Operator step AFTER: DATABASE_URL=... npx a2a-db upgrade
await migratePostgresRuntime({ connectionString: process.env.DATABASE_URL! });
const persistence = await createPostgresPersistence({
  connectionString: process.env.DATABASE_URL!,
  encryptionKey: process.env.CALLBACK_KEY!, // base64-encoded 32-byte key
  delivery: {}, // optional transactional outbox; bounded retries and worker leases
  execution: {}, // optional PostgreSQL leases, scoped journal and remote cancellation
});
const auth = new APIKeyAuth({ identities: { [apiKey]: 'service' } });
const agent = new Agent({ name: 'Durable', description: 'Persistent tasks', profile: 'durable', auth, persistence });
```

Install optional `kysely` and `pg` packages for PostgreSQL. Kysely 0.28.17 preserves Node 20 support;
Kysely 0.29 requires Node 22. The factory uses official SDK `DatabaseTaskStore` and
`DatabasePushNotificationStore`. SDK migrations are operator-run and repeatable; startup only
checks readiness. `taskTable`/`pushTable` customize names and must match migration flags.
The factory closes its own pool on shutdown. Custom external stores remain application-owned.

Callback tokens and authentication credentials are encrypted with AES-256-GCM, bound to their
owner/tenant/task/config/URL, and decrypted only for use. Keep the encryption key outside backups
and retain it for restore. For rotation, supply `encryptionKeys: { blue: oldBase64Key, green: newBase64Key }`
and `activeEncryptionKeyId: 'green'`. Keep `encryptionKey` while legacy v1 rows or backups remain.
New writes carry the active key ID; `rotateCallbackCredentials(taskId, trustedContext)` atomically
rewrites that owner's task configurations under the active key. Roll out readers with both keys
before switching writers; retire keys only after all rows and retained backups can be restored.
Task payloads
remain application data in the database. Public HTTPS, scoped configuration IDs and DNS-pinned
transport protections apply to both memory and SQL callbacks. SQL registration quotas are enforced
under a shared transaction lock (`maxPushConfigsPerTask`, default 8).

With `delivery`, protocol state, its revision, a bounded task journal and callback outbox records
commit in one transaction. Revision checks reject stale writers. Worker leases use PostgreSQL
`SKIP LOCKED`, bounded exponential retry/jitter and dead-letter state. Defaults are 8 attempts,
24 hours maximum age (`maxAgeMs`), 10000 pending records and a 15-second delivery lease.
Expired or crash-exhausted claims become dead without another external attempt; PostgreSQL's
clock determines expiry. Explicit replay starts a fresh retry/age budget. Set `delivery.autoStart: false` during restore or
inspection to prevent automatic outbound delivery; `dispatchOnce()` remains an explicit operator action. Every attempt/replay keeps
the same `X-A2A-Delivery-Id`; delivery is at-least-once and receivers must deduplicate that ID.
`persistence.delivery.status()`, `dispatchOnce()`, `prune(before)` and owner-scoped `replay(id, context)`
provide operator hooks. Replay accepts a trusted authenticated ServerCallContext; do not construct it
from unverified client input. `purgeTask(taskId, before, trustedContext)` is available with the
transactional `delivery` extension: it removes only that owner's terminal task payloads, callbacks
and journal when no deliveries are pending, retaining a small revision tombstone to block stale
resurrection. `maxStoredTasks` limits the default memory store only; SQL deployments must schedule
purge and apply database disk quotas. Snapshot notifications carry the official v1 StreamResponse envelope.

With `execution`, a scoped lease and fencing token guard state writes. Another replica may read,
subscribe to committed task snapshots or cancel the task; a stale worker cannot overwrite its state.
The per-task journal retains the latest 16 snapshots. At the default 4MiB snapshot limit this can
retain up to 64MiB of journal payload per task, plus protocol state and outbox records; choose limits
and a retention schedule for your workload. Resubscription observes live committed state,
not an unlimited historical stream. PostgreSQL failure invalidates leases and stops cooperative work.

After an execution lease expires, a live replica reconciles an interrupted ordinary task to FAILED.
A task with an explicitly saved checkpoint becomes INPUT_REQUIRED for manual continuation; it is
never reported completed merely because its producer disappeared.

Checkpoint recovery is explicit: set `{ task: true, taskContext: true, checkpoint: true }`, use
`task.checkpoint(data)` and inspect `task.checkpointData`. After a crash and lease expiry, send a
follow-up using the same real `taskId`, identity and tenant. Only that opt-in skill interprets its
checkpoint; no scheduler automatically restarts arbitrary code. External side effects require
idempotency keys or their own transaction. This replica/checkpoint extension remains an opt-in
prototype whose tested boundaries are documented in [OPERATIONS.md](https://github.com/xvierd/a2a-lite/blob/main/OPERATIONS.md).

### Dependency security pins

The tested development toolchain uses Vitest/coverage 4.1.12, Express 5.3.0, Supertest 7.3.1 and
uuid 11.1.1. Package overrides pin patched transitive releases for `@humanfs/node`,
`brace-expansion` 1/5, `form-data`, `path-to-regexp` and `rollup`. These address the audit
advisories without `npm audit fix` or a major production framework migration. Revisit the overrides
when their parent packages ship compatible patched dependencies. Consumer applications should
also audit their resolved Express peer and lockfile.

---

## Installation

```bash
npm install a2a-lite
```

**Requirements:** Node.js >= 20

---

## Quick Start

### 1. Create an agent

```typescript
import { Agent } from 'a2a-lite';

const agent = new Agent({
  name: 'Calculator',
  description: 'Does math'
});

agent.skill('add', async ({ a, b }) =>
  Number(a) + Number(b)
);

agent.skill('multiply', async ({ a, b }) =>
  Number(a) * Number(b)
);

await agent.run(); // Listening on http://localhost:8787
```

### 2. Test it (no HTTP needed)

In a test, reuse the agent definition without calling `run()`:

```typescript
import { AgentTestClient } from 'a2a-lite';

const client = new AgentTestClient(agent);
const result = await client.call('add', { a: 2, b: 3 });
expect(result.data).toBe(5);
```

---

## Features

### Skills

```typescript
agent.skill('greet', async ({ name }) =>
  `Hello, ${name}!`
);

// With description and tags
agent.skill('greet', {
  description: 'Greet someone by name',
  tags: ['greeting']
}, async ({ name }) => `Hello, ${name}!`);
```

### Streaming

Use `async function*` to stream responses:

```typescript
agent.skill('chat', { streaming: true }, async function* ({ message }) {
  for (const word of String(message).split(' ')) {
    yield word + ' ';
  }
});
```

### Middleware

Cross-cutting concerns without touching skill code:

```typescript
agent.use(async (ctx, next) => {
  console.log(`Calling: ${ctx.skill}`);
  const result = await next();
  console.log(`Result: ${result}`);
  return result;
});
```

### Authentication

API keys are hashed in memory using SHA-256 — plaintext keys are never stored.

```typescript
import { Agent, APIKeyAuth, BearerAuth } from 'a2a-lite';

// API Key
const agent = new Agent({
  name: 'SecureBot',
  description: 'A secure bot',
  auth: new APIKeyAuth({ keys: ['secret-key'] }),
});

// Bearer token with custom validator
const agent2 = new Agent({
  name: 'JWTBot',
  description: 'JWT-protected bot',
  auth: new BearerAuth({
    validator: async (token) => valid(token) ? 'user-id' : null
  }),
});
```

`valid(token)` represents your application's token verification, including signature,
issuer, audience and expiry checks. For durable ownership across API-key rotation,
use the stable `identities` mapping shown above.

### File Handling

Convert inline file data explicitly; JSON parameters do not preserve class instances:

```typescript
import { FilePart } from 'a2a-lite';

// Call with params: { filename: 'note.txt', raw: Buffer.from('Hello').toString('base64') }
agent.skill('analyze', async ({ filename, raw }) => {
  const file = FilePart.fromA2A({ filename, raw });
  const content = await file.readText();
  return { name: file.name, size: content.length };
});
```

### Lifecycle Hooks

```typescript
agent.onStartup(() => console.log('Agent starting'));
agent.onShutdown(() => console.log('Agent stopping'));
agent.onComplete((skill, result) => console.log(`Completed: ${skill}`));
agent.onError(async (e) => ({ error: e.message }));
```

---

## Testing

`AgentTestClient` lets you test without starting an HTTP server:

```typescript
import { AgentTestClient } from 'a2a-lite';

const client = new AgentTestClient(agent);

// Regular call
const result = await client.call('greet', { name: 'World' });
expect(result.data).toBe('Hello, World!');

// Streaming (collects all chunks)
const results = await client.stream('chat', { message: 'hello world' });
expect(results.length).toBe(2);

// Inspect the agent
const skills = client.listSkills();
const card = client.getAgentCard();
```

`AgentTestClient.call()` returns a `TestResult` with `.data`, `.text`, and `.json()`.
`stream()` collects handler output directly; use a real HTTP client to test SSE,
authentication and injected task contexts together.

---

## Agent Constructor

```typescript
const agent = new Agent({
  name: 'Bot',              // Required
  description: '...',       // Required
  version: '1.0.0',         // Your agent's version; default "1.0.0", independent of the library
  url: undefined,           // Optional, auto-detected
  auth: undefined,          // Optional: APIKeyAuth, BearerAuth
  corsOrigins: ['...'],     // Optional: CORS allowed origins
});
```

## Run Options

```typescript
const runtime = await agent.run({
  host: '0.0.0.0',          // Default
  port: 8787,               // Default
});

// In the host application's shutdown path:
await runtime.stop();
```

---

## Multi-Agent Communication

### TaskHandle -- track remote tasks

When delegating to a remote agent, you can get back a `TaskHandle` that includes the A2A task ID alongside the result. The remote skill must return a Task, for example with `{ task: true }`; a plain Message has no task ID. Use `returnImmediately: true` to obtain the handle while work is still running.

```typescript
import { Agent, AgentNetwork, TaskHandle, getRemoteTask, cancelRemoteTask } from 'a2a-lite';

const network = new AgentNetwork();
network.add('data', 'http://localhost:8787');

const agent = new Agent({ name: 'Orchestrator', description: 'Delegate data requests', network });

agent.skill('process', async ({ query }) => {
  // Get a TaskHandle instead of just the result
  const handle = await agent.delegate('data', 'fetch', { query }, { returnHandle: true }) as TaskHandle;
  console.log(`Task ID: ${handle.taskId}`);
  console.log(`Agent: ${handle.agentUrl}`);
  console.log(`Result: ${handle.result}`);
  return String(handle.result);
});
```

#### Task Lifecycle -- poll and cancel remote tasks

Use convenience methods directly on the handle, or via the network by name:

```typescript
// Poll status directly on the handle
const status = await handle.getStatus();
const status2 = await handle.getStatus(15_000);  // custom timeout in milliseconds

// Or poll via network name
const status3 = await network.getTask('data', handle.taskId);
const status4 = await network.getTask('data', handle.taskId, 15_000);

// Cancel directly on the handle
await handle.cancel();
await handle.cancel(15_000);

// Or cancel via network name
await network.cancelTask('data', handle.taskId);
await network.cancelTask('data', handle.taskId, 15_000);
```

Low-level functions are also available:

```typescript
const status = await getRemoteTask('http://localhost:8787', taskId);
await cancelRemoteTask('http://localhost:8787', taskId);
```

### Client-Side SSE Streaming

When calling a remote streaming agent, consume its chunks as they arrive:

```typescript
import { streamRemoteSkill } from 'a2a-lite';

network.add('story', 'http://localhost:8788');

// Via agent.delegate with stream: true
agent.skill('display', async ({ topic }) => {
  const chunks: string[] = [];
  const stream = await agent.delegate('story', 'tellStory', { topic }, { stream: true });
  for await (const chunk of stream) {
    process.stdout.write(chunk);
    chunks.push(chunk);
  }
  return chunks.join('');
});

// Or directly
for await (const chunk of streamRemoteSkill('http://localhost:8788', 'tellStory', { topic: 'dragons' })) {
  process.stdout.write(chunk);
}
```

### Agent Card Discovery

Fetch a remote agent's card to inspect its capabilities before delegating:

```typescript
import { discoverAgent, AgentCardInfo } from 'a2a-lite';

const card: AgentCardInfo = await discoverAgent('http://localhost:8787');
console.log(`Agent: ${card.name} v${card.version}`);
console.log(`Skills: ${card.skills.map(s => s.name).join(', ')}`);
console.log(`Streaming: ${card.supportsStreaming}`);

// Auto-discover when registering
network.add('data', 'http://localhost:8787', { autoDiscover: true });

// Validate skill exists before delegating
const result = await agent.delegate('data', 'fetch', { query: 'hello' }, { discover: true });
```

### Per-Task Push Notifications

```typescript
import { setTaskPushNotification } from 'a2a-lite';

const credentials = {
  credentialProvider: async () => ({ 'X-API-Key': await readCurrentKey() }),
};
network.add('worker', 'https://worker.example', credentials);
// The remote process skill must return a Task and require authentication.
const handle = await agent.delegate('worker', 'process', { data: '...' }, { returnHandle: true }) as TaskHandle;

// Register webhook for this specific task
await handle.subscribe('https://my-app.com/webhook', 'secret-token');

// Or directly, with the same authenticated owner and configuration ID
await setTaskPushNotification(
  handle.agentUrl, handle.taskId, 'https://my-app.com/webhook',
  'secret-token', 10_000, handle.taskId, credentials
);

// Retrieve / remove
const config = await handle.getPushConfig();
await handle.unsubscribe();
```

---

## CLI

```bash
npx a2a-lite --help
npx a2a-lite init my-agent
npx a2a-lite inspect http://localhost:8787
npx a2a-lite info http://localhost:8787
npx a2a-lite test http://localhost:8787 greet --param name=World
npx a2a-lite discover http://localhost:8787 http://localhost:8788
npx a2a-lite doctor
npx a2a-lite doctor http://localhost:8787
```

| Command | Purpose |
|---------|---------|
| `init <name>` | Scaffold a TypeScript agent project |
| `inspect <url>` | Agent card and skills |
| `info <url>` | Compact plain-text info |
| `test <url> <skill> [--param k=v]` | Call a skill over A2A v1.0 |
| `discover <url...>` | Compare several agents |
| `doctor [url]` | Local env + optional remote v1.0 check |

Python has additional commands (`create`, `serve`); see [packages/python/docs/cli.md](https://github.com/xvierd/a2a-lite/blob/main/packages/python/docs/cli.md).
---

## A2A Protocol Mapping

Everything maps directly to the underlying protocol — no magic, no lock-in.

| A2A Lite | A2A Protocol |
|----------|--------------|
| `agent.skill()` | Agent Skills |
| `agent.run()` | JSON-RPC + REST (HTTP+JSON) server |
| `{ streaming: true }` | SSE / `SendStreamingMessage` |
| `FilePart` | A2A File parts |
| `DataPart` | A2A Data parts |
| `Artifact` | A2A Artifacts |
| `APIKeyAuth` / `BearerAuth` / `OAuth2Auth` | `securitySchemes` on the agent card |
| `signAgentCard` / `verifyAgentCard` | Signed Agent Cards (**experimental**) |
| `AgentNetwork` / `delegate()` | Remote `SendMessage` |
| `TaskHandle` | Task ID + result wrapper |
| `AgentCardInfo` | Agent card metadata |
| `discoverAgent()` | `GET /.well-known/agent-card.json` |
| `getRemoteTask()` | `GetTask` JSON-RPC |
| `cancelRemoteTask()` | `CancelTask` JSON-RPC |
| `streamRemoteSkill()` | Client-side SSE consumer |

Wire methods use **A2A v1.0** names (`SendMessage`, not `message/send`) and the `A2A-Version: 1.0` header.

Full multi-language API: [AGENT.md](https://github.com/xvierd/a2a-lite/blob/main/AGENT.md). CLI deep dive (Python has `create` / `serve`): [packages/python/docs/cli.md](https://github.com/xvierd/a2a-lite/blob/main/packages/python/docs/cli.md).

---

## Examples

TypeScript samples live in [`examples/`](https://github.com/xvierd/a2a-lite/tree/main/packages/typescript/examples) and the repo-root [side-by-side suite](https://github.com/xvierd/a2a-lite/tree/main/examples/typescript).

### Showcase: Battleship (Python demo — same protocol)

Playable multi-agent **A2A v1.0** showcase (implemented in Python with a2a-lite; useful to see real `SendMessage` traffic and a web UI):

```bash
# from repo root
cd examples/python/11_battleship_lite
pip install -e ../../../packages/python
python agent.py    # human vs bot → http://localhost:8790/
# python arena.py  # bot vs bot  → http://localhost:8793/?mode=arena
```

Details: [examples/python/11_battleship_lite/README.md](https://github.com/xvierd/a2a-lite/blob/main/examples/python/11_battleship_lite/README.md)

---

## Full API Reference

See [AGENT.md](https://github.com/xvierd/a2a-lite/blob/main/AGENT.md) for the complete multi-language API reference.

---

## License

MIT
