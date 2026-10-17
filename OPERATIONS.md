# Operating A2A Lite

A2A Lite keeps the first agent small and makes operational guarantees explicit. Start with messages, add tasks when callers need a queryable operation, then enable authentication and persistence as the application needs them. Select a deployment profile by its tested guarantees, not by the number of features enabled.

## Deployment profiles

| Profile | Identity | State | Intended use |
|---|---|---|---|
| `learning` | Authentication optional | Memory by default | Local exercises and disposable demos |
| `authenticated` | Verified, nonempty identity required | Memory allowed | Authenticated integrations whose task state may be discarded on restart |
| `durable` | Verified identity and authorized tenant required | Compatible durable backend required | Persistent tasks and callback configuration; execution recovery depends on the specific backend and skill contract |

The durable profile must fail startup if its database, migrations or required encryption configuration are unavailable. Startup readiness validates active configuration and schema access; it does not establish that every historical encrypted record can be decrypted. Readiness must fail when storage fails or the runtime starts draining. A durable task record does not reconstruct a running function after a crash. Use the language package's documented recovery mode and its failure tests before enabling multiple workers for a stateful skill.

Run one agent implementation per database schema and qualify the SDK/storage versions used by its replicas. Python, TypeScript and Java share wire behavior and identity semantics; their database schemas are independent. Do not point heterogeneous language replicas at the same tables. Mixed-version rolling upgrades require a separate compatibility check.

| Operational capability | Python | TypeScript | Java standalone |
|---|---|---|---|
| Database setup | `PersistenceConfig.migrate()` | Official `a2a-db upgrade`, then `migratePostgresRuntime()` for extensions | `JdbcProtocolBackend.initializeSchema()` |
| Atomic callback handoff | Managed SQL event trigger and outbox | Explicit `delivery` option | JDBC task-revision outbox |
| Cross-replica task events and cancellation | SDK database event stream and versioned task store | Explicit `execution` option, with `delivery` | JDBC revision journal and cancellation relay |
| Ordinary worker crash | Task becomes failed after lease expiry | Task becomes failed after lease expiry | Task becomes failed after lease expiry |
| Opt-in checkpoint recovery | `recoverable=True` reruns from the beginning with a checkpoint | Explicit continuation of a checkpoint-enabled skill | Application-managed `CheckpointLeases` primitive |
| Default execution lease | 30 seconds | 15 seconds | 5 seconds |

The coordination extensions are opt-in reference implementations. A durable-state profile alone
does not guarantee distributed execution. Python additionally supports SQLite for a single-host
tutorial. TypeScript and Java expose persisted snapshot journals for subscriptions; they do not promise
unlimited event replay. TypeScript bounds retained snapshots; Java revisions require scheduled
`purgeFinalizedBefore()` cleanup, which preserves pending and failed deliveries. Use the package guides for configuration and API details:
[Python](packages/python/docs/production.md), [TypeScript](packages/typescript/README.md#postgresql-transactional-delivery-and-replica-coordination),
[Java](packages/java/README.md).

## Stable identities and tenant authorization

Map rotating API keys to an explicit principal such as `alice`. A key hash is useful for a small demo but changes when the key changes. During rotation, accept both keys for the same principal, verify that the new key can read existing tasks, then revoke the old key.

Use a verified issuer as the identity namespace for OAuth. The same subject from two issuers represents two different principals. Custom authentication providers must return the namespace and tenant memberships from trusted configuration or verified claims. A request's tenant field never grants membership by itself.

Identity keys preserve the original nonblank user ID, including leading or trailing whitespace. Namespaced identities use `a2a:v1:` followed by base64url of the compact UTF-8 JSON pair `[namespace, userId]`, without padding. Legacy IDs beginning with that prefix are escaped as `[null, originalUserId]`. This prevents a legacy ID from impersonating an encoded principal. Existing records using a raw reserved-prefix ID need an explicit ownership migration.

Default identities can access only the default tenant. Additional tenants require an explicit authorized set. Where an SDK does not partition storage by tenant, the owner key encodes `["owner", tenant, principalKey]` using the same prefix. The shared [identity vectors](tests/contracts/identity.json) define the encoding; storage adapters must still authorize membership before deriving a key.

Supply outbound credentials in headers or a credential provider. Providers run for each request, including discovery and task helpers, so credential rotation applies to an existing handle. Credentials are bound to the original origin. A discovered cross-origin URL needs an explicit trusted-origin policy; HTTP redirects do not carry credentials to a new destination.

## Tasks and runtime lifecycle

An immediate Message does not create a queryable Task or support a TaskHandle; a wire-level `message.taskId` alone is insufficient. Request task mode for an ordinary skill when callers need GetTask, cancellation, subscriptions or a TaskHandle. A skill's protocol TaskContext ID must be the same ID a remote caller receives. Application-local task stores remain separate from protocol persistence.

Embed an agent through its managed `start` operation and close the returned runtime during application shutdown. The executable application owns process signals. Stopping one agent must not terminate another agent or the host process. A graceful shutdown first refuses new work, then waits for accepted work within its configured grace period, and finally reports or reconciles interruptions.

Set finite admission, stream, payload, execution and retention limits for the workload. Admission limits bound accepted work; they are separate from the thread or connection pool size. In Java, preserve the SDK's producer/consumer separation so event consumers can finish while task admission is saturated. Cooperative cancellation requires skills to observe their cancellation context. Blocking or uncooperative code needs a process or worker boundary for hard termination.

## Health and diagnostics

Probe `/health/live` to check that the HTTP runtime responds and `/health/ready` before routing work to it. A failed readiness check should remove the replica from traffic without immediately deleting durable state. Keep health responses small and free of credentials, connection strings or task contents.

Observe active work, admission rejection, task latency, failed storage operations and callback backlog. Use bounded labels such as operation, outcome and runtime profile. Keep task IDs, user IDs and tenant IDs out of metric labels; attach necessary correlation IDs to access-controlled structured logs or trace context instead. An observer failure must not change a task result.

## Callback delivery and receiver deduplication

Durable delivery needs an atomic handoff: the accepted task event and its pending delivery must commit together. A network sender added after an ordinary store save leaves a crash window. Use only the durable adapter's tested transaction or persisted-event mechanism for this guarantee.

Treat delivery as at least once. A receiver should use the Lite extension header `X-A2A-Delivery-Id` as an idempotency key: commit the business effect and that ID in one transaction, then return success. If the sender crashes after the receiver commits but before recording the acknowledgment, the retry carries the same ID. Replaying a failed delivery must retain that identity.

Deleting a subscription stops future queued attempts. A request already in flight may finish. Retain failed-delivery records long enough to diagnose and replay them, and apply a bounded retry count and delivery age. Replay only after correcting the receiver or its credentials; a permanent authorization error should not become an infinite retry loop.

Every attempt must retain public-HTTPS validation, pinned validated DNS, TLS hostname verification, disabled redirects/proxies and bounded response handling. Keep notification tokens and configured headers encrypted in storage and absent from logs. Retain old decryption keys until no active configuration or retained delivery references them; rotate by introducing a new key ID and re-encrypting through the adapter's supported operation.

## Backup, upgrades and incidents

Back up the database and the external encryption-key configuration separately. Test restoration into an isolated database with the same schema version. Keep automatic callback dispatch disabled during validation (Java: `automaticDelivery=false`). Verify task reads, owner and tenant isolation, configuration decryption and queued-delivery identities before allowing restored workers to send callbacks. A database dump without the necessary decryption keys cannot recover callback secrets.

During a rolling upgrade, keep overlapping workers on compatible schema and event formats. Run migrations before accepting new work, retain a rollback-compatible application version, and avoid destructive schema changes until old workers have drained. Do not roll back to code that derives different ownership keys without an explicit data migration.

| Incident | First action | Verify before reopening traffic |
|---|---|---|
| Admission saturation | Inspect active work and dependency latency; reduce incoming concurrency | Queues and active tasks return below configured limits |
| Database outage | Keep readiness false and stop accepting durable work | Writes, reads and ownership checks succeed; failures were not acknowledged as persisted |
| Callback receiver outage | Inspect retry age and permanent failures; repair receiver | Retry retains its delivery ID and deleted subscriptions remain inactive |
| Worker crash | Let the declared reconciliation or checkpoint mode handle accepted tasks | Interrupted tasks become explicit; a stale owner cannot overwrite a successor |
| Restore or rollback | Isolate workers and outbound callback dispatch | Access control, schema compatibility and deduplication survive restoration |

## Qualification

The [1.2.0 local evidence](tests/evidence/2026-10-17-1.2.0/README.md) records measured results and remaining qualification.

Run the [interoperability gates](tests/interop/README.md) against the exact code and SDK versions being deployed. The nine Lite client/server combinations cover the common JSON-RPC surface. The official Python SDK additionally validates AgentCard parsing, messages, task reads and SSE. REST and optional gRPC need their own transport tests; Java standalone advertises JSON-RPC only.

Use the load runner to record hardware, workload, concurrency, throughput, p95/p99 and error rate. Its loopback memory profile measures framework behavior with a 20ms simulated I/O operation; it does not measure a database, TLS, a remote LLM or a production network. Establish latency, availability, recovery-time and acceptable-data-loss targets for the actual deployment before making a production capacity claim.

Run the [dependency checks](tests/security/README.md) on the resolved deployment environment as well
as the package development environment. Keep scan dates and dependency versions with test results.
The expanded CI and release definitions are currently [prepared drafts](.github/workflow-drafts/README.md)
until the repository credential can update active workflows; local results must not be presented as
successful runs of those inactive jobs.
