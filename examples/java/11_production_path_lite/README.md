# Java: learning to a durable service

Java 17+, the repository Gradle wrapper, and PostgreSQL 17 for the durable steps. This example uses no LLM or external callback. Run from `examples/java`; use a second terminal for the client.

```bash
./gradlew :11_production_path_lite:run --args='learning'
./gradlew :11_production_path_lite:run --args='client'
```

The client receives a normal Message, creates a protocol Task whose result equals its real ID, reads that Task with `handle.get()`, then consumes three ordered stream chunks. `SkillConfig.withTask()` is another way to force Task mode for an ordinary one-argument handler.

For identified ownership, set a development `A2A_API_KEY` in both terminals and run `--args='authenticated'`. Optional `A2A_NEXT_API_KEY` maps to the same subject on the server; switch the client key to prove rotation retains task access. The example binds loopback. Use TLS at your ingress before serving credentials externally. Credentials are evaluated per request and scoped to the explicitly configured endpoint; redirects are disabled.

For persistent protocol tasks, provide `A2ALITE_POSTGRES_DSN` (a JDBC PostgreSQL URL), `A2ALITE_POSTGRES_USER`, `A2ALITE_POSTGRES_PASSWORD`, and `A2A_CALLBACK_KEY_BASE64` (a separately stored random AES key, base64 encoded, 16/24/32 bytes). Run `--args='durable'`. Restart with the same database and key to keep tasks and their ownership. Use a bounded connection pool in a deployed application; `PGSimpleDataSource` keeps this example's dependencies small. Move `initializeSchema()` into a controlled migration step and remove DDL permission from the application role.

`GET /health/live`, `GET /health/ready`, and `GET /metrics` expose process health, backend readiness and bounded admission counters. `Agent.start()` returns an `AutoCloseable` handle. Closing it rejects new work, drains for the configured grace period and interrupts remaining work. Java interruption is cooperative: an uncooperative handler requires process/container isolation. Its slot remains occupied while it still runs.

The JDBC prototype provides cross-replica reads, durable snapshot subscriptions and cancellation relay. Execution leases renew every 500 ms and expire after 5 seconds; another running replica reconciles interrupted workers to `FAILED`. Functions are never automatically rerun. `--args='checkpoint'` demonstrates opt-in recovery from an explicit checkpoint with a larger fencing token; stale writes fail. External effects still require idempotency or downstream fencing.

Callbacks use an atomic task-revision outbox and encrypted config. `X-A2A-Delivery-Id` stays stable across retries; receivers deduplicate it. Delivery is at least once. Deleting a config cancels queued attempts, while an already in-flight request can finish. Failed attempts back off with jitter and become dead letters after eight claims or 24 hours; worker crashes before acknowledgment consume claims too. `backend.outbox().retryDeadLetters()` is an explicit operator action. `purgeFinalizedBefore(cutoff,batchSize)` retains tasks with undelivered/dead-letter callbacks.

Tests against real PostgreSQL cover restart/owner proof, rollback between task and outbox, delivery retry and lease recovery, two-replica HTTP subscription/cancel, interrupted-worker reconciliation and stale-writer fencing. See repository `OPERATIONS.md` for reproducible interoperability, load and backup/restore gates. These are bounded reference/prototype guarantees, not an automatic enterprise certification.
