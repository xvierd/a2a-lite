# 10 — Persistence Lite: pluggable TaskStore + PushNotifier

This example shows how to wire a custom **protocol-level TaskStore** and a
**PushNotifier** into an A2A Lite agent.

## What each piece does

| Piece | What it does |
|---|---|
| `protocol_task_store` | Stores A2A protocol task state (status, results). Pass any `TaskStore` implementation — swap `InMemoryTaskStore` for Redis/Postgres in production. |
| `push_notifier` | Called automatically after every skill completes. Two built-in options: `LogPushNotifier` (logs to stdout) and `WebhookPushNotifier` (POSTs JSON to a URL). |
| `LogPushNotifier` | Zero-config notifier for development. Events are written to the Python logger. |
| `WebhookPushNotifier` | Production notifier. Reads `WEBHOOK_URL` from env, optionally signs each request with HMAC-SHA256 when `WEBHOOK_SECRET` is set. Retries on transient failures. |

## Skills

| Skill | Description |
|---|---|
| `echo` | Returns the input message unchanged. Simple sanity check. |
| `slow_sum` | Adds two integers after an async sleep. Demonstrates that push notifications fire even for slow, long-running tasks. |

## How to run

### Development (no external service needed)

```bash
cd examples/python/10_persistence_lite
pip install a2a-lite
python agent.py
```

The agent starts on **port 8793**. All task-completion events are logged to
the console via `LogPushNotifier`.

### Production (with webhook)

```bash
WEBHOOK_URL=https://hooks.example.com/a2a python agent.py
```

Each completed skill POSTs a JSON payload to the webhook:

```json
{
  "skill": "slow_sum",
  "result": {"a": 3, "b": 4, "sum": 7, "delay_seconds": 1.0}
}
```

### With HMAC request signing

```bash
WEBHOOK_URL=https://hooks.example.com/a2a \
WEBHOOK_SECRET=mysecret \
python agent.py
```

Every request will include an `X-A2A-Signature: sha256=<hex>` header. Verify
it on your server with:

```python
import hashlib, hmac

def verify(body: bytes, secret: str, header: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return header == f"sha256={expected}"
```

## Extending to a real persistent store

Replace `InMemoryTaskStore()` with your own implementation that satisfies the
`a2a.server.tasks.TaskStore` interface:

```python
from myapp.stores import RedisTaskStore

protocol_store = RedisTaskStore(url=os.getenv("REDIS_URL"))

agent = Agent(
    name="MyAgent",
    description="...",
    protocol_task_store=protocol_store,
    push_notifier=push_notifier,
)
```