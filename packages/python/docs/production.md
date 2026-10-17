# From learning to a managed deployment

The [executable progression](../../../examples/python/12_production_path) runs without an LLM or external service. The default API remains `Agent(...); @agent.skill(...); agent.run()`. Choose guarantees explicitly when you add persistence or multiple replicas.

## Task identity and credentials

```python
from a2a_lite import Agent, AgentNetwork, ClientConfig, RuntimeConfig, TaskContext
from a2a_lite.auth import APIKeyAuth

agent = Agent(
    "Worker", "Authenticated tasks",
    auth=APIKeyAuth(principals={"old-key": "alice", "new-key": "alice"},
                    namespace="my-service", authorized_tenants={"team-a"}),
    runtime=RuntimeConfig(profile="authenticated"),
)

@agent.skill("work", task=True)
async def work(task: TaskContext):
    return task.task_id

network = AgentNetwork()
network.add("worker", "https://worker.example", client_config=ClientConfig(
    headers={"X-API-Key": "new-key"}, tenant="team-a",
))
# handle = await network.call("worker", "work", return_handle=True)
# assert handle.result == handle.task_id
# await handle.get_status()  # carries the same credential/tenant context
```

`task=True`, a `TaskContext` parameter, or streaming produces a real SDK Task. Ordinary functions keep returning Messages. Local `task_store="memory"` is an optional application mirror and is no longer required for `TaskContext`.

`ClientConfig(credential_provider=...)` accepts a sync/async function receiving the destination URL and returning request headers. It runs for discovery, every RPC, SSE, task operation and callback configuration. Credentials default to the original origin; redirects are disabled. A different origin advertised by a card is rejected before forwarding credentials. Explicit `allowed_origins=frozenset({"https://trusted.example"})` permits a trusted second origin. Task handles preserve that binding and tenant.

`AuthResult` adds trusted `namespace` and `authorized_tenants`. The default authorized set is only `{""}`. OAuth derives its namespace from the configured, verified issuer; an optional `tenant_claim` must be a verified list of tenant strings. NoAuth remains anonymous and can only use the default tenant. A provider's successful result must have a valid nonblank string identity. Profiles other than learning reject an anonymous fallback from CompositeAuth.

Principal IDs preserve legacy exact user IDs unless a namespace exists or the ID starts with `a2a:v1:`. These cases use `a2a:v1:` plus unpadded base64url of compact UTF-8 JSON `[namespace-or-null,userID]`. A nonempty tenant uses the same prefix with `["owner",tenant,principalKey]` at the SDK store boundary. A raw legacy ID starting with the reserved prefix needs a storage-key migration. Managed SQL hashes the complete scoped key to a fixed-width SHA-256 key for the SDK's 255-character owner column. Different languages do not share SQL schemas.

## Profiles and lifecycle

| Profile | Authentication | State |
|---|---|---|
| `learning` (default) | NoAuth allowed | Memory allowed |
| `authenticated` | Verified identity required | Memory explicitly allowed |
| `durable` | Verified identity required | `PersistenceConfig` required; no memory fallback |

```python
runtime = await agent.start(host="127.0.0.1", port=0)
try:
    print(runtime.url, runtime.ready, runtime.stats)
finally:
    await runtime.stop()
```

The returned `ManagedRuntime` owns HTTP, SDK tasks/subscribers, callback clients, database pools and workers. Startup/shutdown hooks run on the same event loop. An embedded runtime does not register process signal handlers. `agent.run()` remains the blocking CLI entry point. `build_grpc_server()` returns the equivalent managed experimental gRPC server; await `start()` and `stop()`.

`GET /health/live` returns a minimal live flag. `/health/ready` is 503 before startup, while draining or when schema/storage checks fail. Statistics expose counts, never credentials or message payloads. Admission covers the entire execution lifetime, including work continuing after `returnImmediately`; active stream subscriptions have a separate limit.

`RuntimeConfig` defaults: 64 concurrent executions, 16 executions per scoped principal, 128 streams, 1 MiB request/event limits, 8 MiB cumulative protobuf output per execution, 16 callback configurations per task, 100 retained history messages, 128 retained artifacts, 300 second execution deadline and 10 second shutdown grace. Snapshot retention keeps the newest entries; the durable event log is separately retained. JSON/base64 encoding can make wire output larger than protobuf sizes. A skill must yield control and cooperate with cancellation. Python cannot forcibly terminate a blocking or cancellation-resistant function: bounded shutdown reports `uncooperative` and the host must isolate/terminate such workers. The default in-memory store retains up to 10,000 tasks, expires terminal tasks after one hour and evicts the oldest terminal task at capacity; it never evicts active tasks. External SQL retention uses the explicit cleanup operation below. Each shutdown phase is bounded separately: drain, cancellation acknowledgment, SDK close, shutdown hooks and backend close can each consume the configured grace; transport shutdown can add its own grace. Persistent shutdown revokes this runtime's execution fences before disposing its pool, and locally rejects further checkpoint/effect writes even if a handler ignores cancellation. If revocation cannot finish because storage is unavailable or a transaction holds a lock, shutdown reports uncooperative work and the pool may remain undisposed; the host must isolate such workers and let the database lease expire. Synchronous code that blocks the event loop still requires process isolation.

## SQL state, events and migrations

```bash
pip install 'a2a-lite[postgresql]'
# Or: pip install 'a2a-lite[sqlite]' for a single-host tutorial
```

```python
import os
from a2a_lite import PersistenceConfig

storage = PersistenceConfig(
    os.environ["A2ALITE_DATABASE_URL"],
    encryption_key=os.environ["A2ALITE_ENCRYPTION_KEY"],
    encryption_key_id="2026-10",   # nonsecret key identifier
    schema="agents",              # optional PostgreSQL schema
)
await storage.migrate()            # deployment step before starting replicas
# Add persistence=storage and runtime=RuntimeConfig(profile="durable") to Agent.
```

Use `postgresql+asyncpg://...` or `sqlite+aiosqlite:///...`. A stable external Fernet key is mandatory; do not generate a new key on each restart. `PersistenceConfig.build()` exposes a trusted operator backend for migrations/tests. `runtime.storage` exposes the running backend for operational actions.

The adapter composes the official SDK **1.2.2** `VersionedDatabaseTaskStore`, `DatabaseTaskEventStream` and encrypted `DatabasePushNotificationConfigStore`. Schema v1 adds callback, execution-lease and protected-effect tables plus triggers; snapshot/version/event writes stay in the SDK transaction. Startup validates the version, tables and required triggers. Changes to the SDK's SQL models require running the schema/transaction tests before rollout. Migrations are explicit and idempotent; run one migrator before replicas, back up first and preserve compatible old code/schema for rollback. No automatic destructive downgrade is provided.

PostgreSQL is the multi-replica qualification target. SQLite is tested for restart and transaction semantics on one host; it is not a multi-host database. Pool readiness is checked dynamically. SQL task/event contents may contain application data: apply database access control, encrypted storage/backups and an application retention policy.

`await runtime.storage.cleanup(older_than_utc_datetime)` removes up to 500 old terminal tasks and their events/configurations/effects. It preserves tasks with pending, sending or dead-letter callbacks. Run repeatedly to complete a maintenance batch; active tasks are preserved. The SDK event stream has no built-in expiry.

## Durable callbacks

Dynamic callbacks still require an authenticated task owner and a public HTTPS destination. Registration and every attempt validate the destination, bound DNS resolution and pin the resolved public address while retaining TLS hostname validation. Redirects and environment proxies are disabled. Delivery has a whole-operation 10 second deadline and does not buffer the callback's response body. Credentials and URLs are absent from delivery logs.

A database trigger inserts the encrypted callback snapshot and protocol event into the outbox **in the same transaction** as the SDK task event. There is no cursor over globally assigned sequence IDs, which could skip an earlier transaction that commits late. A separate worker claims deliveries with expiring leases; PostgreSQL uses `FOR UPDATE SKIP LOCKED`. A crash after send but before acknowledgment can repeat a delivery. Receivers must deduplicate the stable Lite extension `X-A2A-Delivery-Id`; payloads and `application/a2a+json` remain A2A v1.0. Ordering across worker attempts is not promised.

Defaults: 5 claims/attempts, exponential retry with jitter, maximum age 24 hours and a 30 second delivery lease. `callback_stats()` exposes counts and `retry_dead(delivery_id)` permits a trusted operator to replay a dead delivery with the same identity. Replay resets the attempt counter and `created_at` age window using the database clock, including deliveries that expired by age. It is not a public unauthenticated endpoint. Deleting a subscription cancels queued/dead attempts transactionally; an already in-flight request can finish.

Key envelopes carry the nonsecret key ID. To rotate, deploy all readers with the new current key and `previous_encryption_keys={"old-id": old_key}`, then call `rotate_encryption()` to re-encrypt callback configurations, outbox snapshots, execution requests, checkpoints and protected-effect results in bounded batches. Stop old-key writers and complete a final rotation pass before removing old keys. Unknown keys/corrupt envelopes fail closed, without a plaintext fallback.

## Recovery is explicit

```python
@agent.skill("batch", recoverable=True)
async def batch(task: TaskContext):
    checkpoint = task.checkpoint_data or {"next": 0}
    for index in range(checkpoint["next"], 10):
        # Perform idempotent work for this index.
        await task.checkpoint({"next": index + 1})
    return "finished"
```

Recoverable skills require managed persistence and return one result; recoverable streaming is rejected. On worker loss, another replica claims the expired execution lease and **runs the handler from its beginning**, with the last committed `checkpoint_data`. Checkpoints are bounded JSON, encrypted at rest. Lease tokens are injected from trusted execution context at the store boundary and checked by database triggers. Stale workers cannot overwrite the successor's task state or update checkpoints.

A skill may `await task.update("input-required", "Please provide an answer")` (or `"auth-required"`) and return. This preserves the paused state without automatically completing the task. A subsequent `SendMessage` with the same `taskId` and authorized principal/tenant runs the handler again with the new input and the saved checkpoint. The database atomically issues a new fence; paused tasks are not picked up by crash recovery. Completed, failed, canceled and rejected tasks cannot be continued.

`await task.effect_once("stable-key", operation)` runs an async operation receiving this database's `AsyncConnection`, and commits its JSON result in the same transaction. On replay it returns the saved result. This protects same-database effects only. Never put email, payment, HTTP calls or another database's writes inside that callback; those need an external idempotency/transaction protocol. A checkpoint alone does not prevent a repeated external effect.

The database clock is authoritative for execution and delivery leases, retry due times and callback expiry; worker wall-clock skew cannot grant a lease. Execution leases default to 30 seconds; recovery polls every 0.1 seconds. A nonrecoverable execution becomes an explicit failed/interrupted Task after lease expiry. Repeated recovery failures are bounded by `max_recovery_attempts` (3 by default). Remote cancellation uses the SDK's versioned task store and shared events. Producers observe cancellation on an event conflict or lease heartbeat. Schema persistence alone never resumes arbitrary Python coroutines.

## Verification

```bash
cd packages/python
uv sync --extra dev --extra oauth --extra grpc --extra sqlite --extra postgresql
uv run pytest --cov=a2a_lite
A2ALITE_POSTGRES_DSN='postgresql+asyncpg://...' uv run pytest tests/test_persistence.py
uv run ruff check src tests
uv run ruff format --check src tests
```

The PostgreSQL tests create/drop an isolated schema. Shared [interop and operational harnesses](../../../tests/interop/README.md) additionally check real processes, cross-language wire behavior and backup/restore. Evidence from these tests is a deployment gate, not a universal throughput or availability guarantee.
