# 10 — Persistence Lite: pluggable TaskStore + PushNotifier

This example shows how to wire a custom **protocol-level TaskStore** and a
**PushNotifier** into an A2A Lite agent.

It uses memory storage and trusted agent-level notifications. For the 1.2.0 managed SQL, durable callback and recovery path, start with [example 12](../12_production_path/) and the [deployment guide](../../../packages/python/docs/production.md). This example's ordinary skills return Messages, so they do not demonstrate queryable Task IDs; use `task=True` or an injected `TaskContext` for those.

## What each piece does

| Piece | What it does |
|---|---|
| `protocol_task_store` | Advanced SDK `TaskStore` extension point. Custom stores must honor request ownership and tenant scope; changing only the store does not provide shared event streams, durable callbacks or execution recovery. |
| `push_notifier` | Called automatically after every skill completes. Two built-in options: `LogPushNotifier` (logs to stdout) and `WebhookPushNotifier` (POSTs JSON to a URL). |
| `LogPushNotifier` | Zero-config notifier for development. Events are written to the Python logger. |
| `WebhookPushNotifier` | Trusted agent-level notifier configured by the application. Reads `WEBHOOK_URL`, optionally signs with HMAC-SHA256 via `WEBHOOK_SECRET`, and retries within the process. It has no durable outbox. |

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

### Trusted Application Webhook

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
    return hmac.compare_digest(header, f"sha256={expected}")
```

## Moving to Managed Persistence

Install `a2a-lite[sqlite]` for a single-host tutorial or `a2a-lite[postgresql]` for the qualified multi-replica path. Configure `PersistenceConfig` with a stable encryption key, run its explicit migration, and use authenticated principals with `RuntimeConfig(profile="durable")`. The [deployment guide](../../../packages/python/docs/production.md) covers the complete configuration and operational limits.

Dynamic per-task callbacks use the authenticated A2A push configuration operations and public HTTPS destinations. With managed SQL they use the transactional outbox and standard protocol payloads; the custom `{skill, result}` envelope above belongs only to the agent-level notifier. Recovering execution additionally requires `recoverable=True` and explicit checkpoint/idempotency design; durable state alone cannot resume arbitrary work.
