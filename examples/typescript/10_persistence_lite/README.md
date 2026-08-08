# 10 — Persistence Lite: Pluggable TaskStore + PushNotifier

Shows how to wire an explicit `protocolTaskStore` and a `pushNotifier` into
an A2A Lite agent.

## What this example demonstrates

| Feature | Where |
|---|---|
| `InMemoryTaskStore` passed as `protocolTaskStore` | Agent config |
| `LogPushNotifier` (dev) / `WebhookPushNotifier` (prod) | `buildPushNotifier()` |
| HMAC-signed webhook payload | `WEBHOOK_SECRET` env var |
| Two skills: `echo` (fast) + `slowSum` (async) | `agent.skill(...)` |
| Startup/shutdown hooks for observability | `agent.onShutdown(...)` |

## Run in dev mode

```bash
cd examples/typescript/10_persistence_lite
npm install
npm start          # or: npx tsx agent.ts
```

The `LogPushNotifier` will print every completion event to stdout.

## Run with a real webhook

```bash
WEBHOOK_URL=https://your.server/hook \
WEBHOOK_SECRET=my-signing-secret \
npm start
```

Every time a skill finishes, the agent POSTs a JSON payload to your webhook:

```json
{
  "skill": "slowSum",
  "result": { "sum": 7, "delayMs": 1000 },
  "timestamp": "2025-01-01T12:00:00.000Z"
}
```

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
const myStore = new MyRedisTaskStore({ ... }); // implements SDK TaskStore

const agent = new Agent({
  protocolTaskStore: myStore,
  // ...
});
```

Replace `new SdkTaskStore()` with any object that satisfies
`@a2a-js/sdk/server`'s `TaskStore` interface and the SDK layer will use it
transparently.
