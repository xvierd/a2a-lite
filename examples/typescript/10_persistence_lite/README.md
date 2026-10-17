# 10 — Persistence Lite: Pluggable TaskStore + PushNotifier

Shows how to wire an explicit `protocolTaskStore` and a `pushNotifier` into
an A2A Lite 1.2.0 agent. Both stores in this example are in memory and reset on
restart. Its two ordinary skills return Messages, so they do not create queryable
protocol Tasks. For real task IDs and PostgreSQL persistence, continue with the
[progressive production example](../11_production_path/README.md).

## What this example demonstrates

| Feature | Where |
|---|---|
| `InMemoryTaskStore` passed as `protocolTaskStore` | Agent config |
| `LogPushNotifier` (console) / `WebhookPushNotifier` (webhook) | `buildPushNotifier()` |
| HMAC-signed webhook payload | `WEBHOOK_SECRET` env var |
| Two skills: `echo` (fast) + `slowSum` (async) | `agent.skill(...)` |
| Registered shutdown hook | `agent.onShutdown(...)`; invoked by managed runtime shutdown |

## Run in dev mode

```bash
# From the repository root, build the local package first.
npm --prefix packages/typescript ci
npm --prefix packages/typescript run build
cd examples/typescript/10_persistence_lite
npm install
npm run typecheck
npm start          # or: npx tsx agent.ts
```

The example's `.npmrc` installs the local `a2a-lite` package with a shared SDK
dependency tree, avoiding incompatible duplicate SDK types from symlinked installs.

The `LogPushNotifier` will print every completion event to stdout.

The library does not install process signal handlers. To invoke the registered
shutdown hook, replace the example's final `agent.run(...)` with application-owned
shutdown handling:

```typescript
const runtime = await agent.run({ port: 8790 });
for (const signal of ['SIGINT', 'SIGTERM'] as const) {
  process.once(signal, () => {
    void runtime.stop().catch(console.error);
  });
}
```

## Run with a real webhook

```bash
WEBHOOK_URL=https://your.server/hook \
WEBHOOK_SECRET=my-signing-secret \
npm start
```

Every time a skill finishes, the agent POSTs a JSON payload to your webhook:

`WebhookPushNotifier` accepts public HTTP(S) destinations, rejects private/reserved
addresses and does not follow redirects. Use a public HTTPS callback for the signed
webhook. Protocol per-task subscriptions separately require an authenticated owner,
a real A2A task and a public HTTPS callback. They use the SDK's owner/tenant-scoped
configuration API and v1.0 notification envelope.

```json
{
  "skill": "slowSum",
  "result": { "sum": 7, "delayMs": 1000 },
  "status": "completed",
  "timestamp": 1760000000,
  "agent": "PersistenceLiteAgent"
}
```

`timestamp` is Unix time in seconds.

When `WEBHOOK_SECRET` is set, the request also carries an
`X-A2A-Signature: sha256=<hex>` header you can verify with HMAC-SHA256.

## Calling the skills (A2A v1.0 wire)

```bash
# Agent card (v1.0 well-known path)
curl -s http://localhost:8790/.well-known/agent-card.json

# echo
curl -s -X POST http://localhost:8790/ \
  -H 'Content-Type: application/json' \
  -H 'A2A-Version: 1.0' \
  -d '{"jsonrpc":"2.0","id":1,"method":"SendMessage","params":{"message":{"messageId":"m1","role":"ROLE_USER","parts":[{"text":"{\"skill\":\"echo\",\"params\":{\"message\":\"hello\"}}"}]}}}'

# slowSum (waits 2 seconds, then push notification fires)
curl -s -X POST http://localhost:8790/ \
  -H 'Content-Type: application/json' \
  -H 'A2A-Version: 1.0' \
  -d '{"jsonrpc":"2.0","id":2,"method":"SendMessage","params":{"message":{"messageId":"m2","role":"ROLE_USER","parts":[{"text":"{\"skill\":\"slowSum\",\"params\":{\"a\":3,\"b\":4,\"delayMs\":2000}}"}]}}}'
```

## Swapping the store

The key pattern is:

```typescript
import { Agent } from 'a2a-lite';
import type { TaskStore } from '@a2a-js/sdk/server';

function createAgent(protocolTaskStore: TaskStore) {
  return new Agent({
    name: 'CustomStore',
    description: 'An application-provided protocol store',
    protocolTaskStore,
  });
}
```

Replace `new SdkTaskStore()` with any object that satisfies
`@a2a-js/sdk/server`'s `TaskStore` interface. Its load/save/list operations must
preserve the SDK's owner and tenant scope; an unscoped store can expose other users'
tasks. This is separate from the Lite `taskStore` compatibility mirror used by
`TaskContext`. Register a skill with `{ task: true, taskContext: true }` to persist
its real protocol task ID and progress. A custom `protocolTaskStore` alone does not
satisfy the `durable` profile: use the supported `ProtocolPersistence` adapter as
shown in [example 11](../11_production_path/README.md).
