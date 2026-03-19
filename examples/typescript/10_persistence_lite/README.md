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
npx tsx examples/typescript/10_persistence_lite/agent.ts
```

The `LogPushNotifier` will print every completion event to stdout.

## Run with a real webhook

```bash
WEBHOOK_URL=https://your.server/hook \
WEBHOOK_SECRET=my-signing-secret \
npx tsx examples/typescript/10_persistence_lite/agent.ts
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

## Calling the skills

```bash
# echo
curl -s -X POST http://localhost:8790/ \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"message/send","params":{"message":{"messageId":"m1","role":"user","parts":[{"kind":"text","text":"{\"skill\":\"echo\",\"params\":{\"message\":\"hello\"}}"}]}}}'

# slowSum (waits 2 seconds, then push notification fires)
curl -s -X POST http://localhost:8790/ \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":2,"method":"message/send","params":{"message":{"messageId":"m2","role":"user","parts":[{"kind":"text","text":"{\"skill\":\"slowSum\",\"params\":{\"a\":3,\"b\":4,\"delayMs\":2000}}"}]}}}'
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
