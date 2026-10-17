# Cross language interoperability and load gates

These gates start local authenticated servers and exercise the public APIs over HTTP. They need no LLM account and do not send external callbacks. Test credentials are disposable constants. A selected runtime that is missing or a failed assertion causes a nonzero exit; omitted languages are not counted as tested.

## Setup

From the repository root, install the package development dependencies and compile the Java fixture:

```sh
uv sync --project packages/python --extra dev --extra postgresql --extra sqlite
npm ci --prefix packages/typescript
cd packages/java
./gradlew writeInteropClasspath
cd ../..
```

Use Node 20 or newer and JDK 17 or newer. Set `JAVA_HOME` if `java` does not select the required JDK. Set `A2ALITE_TEST_PYTHON` to an installed Python interpreter if not using `packages/python/.venv/bin/python`.

## Protocol matrix

```sh
python3 tests/interop/run.py --output /tmp/a2alite-interop.json
```

Each language client calls each language server: nine pairings. Each pairing checks immediate messages, explicit tasks, the identity of the Task inside the skill and remote GetTask, and ordered streaming. Shared probes check discovery, anonymous rejection, credential rotation, cross-user Get/List/Cancel and callback access, configuration IDs, the first SSE Task snapshot, preserved JSON-RPC IDs and skill failure. The official Python SDK parses every AgentCard and exercises each server's messaging/task/stream APIs independently of the Lite clients.

For a focused check, pass `--languages python typescript` or `--languages java`. `--skip-protocol` is a diagnostic option and does not qualify the shared protocol or official-SDK gates.

## Local load measurement

```sh
python3 tests/interop/load.py --requests 200 --concurrency 8 \
  --output /tmp/a2alite-load.json
```

The runner measures immediate messages, completed tasks, 20ms simulated I/O and three-event streams. It records successful requests per second, p50/p95/p99 latency, error rate, response bytes, operating system, CPU count and Git state. Warmup requests are excluded. Error responses and failed Tasks cannot count as successful work.

Use `--workloads message io` or `--languages python` to focus a run. Keep the exact output with the commit and dependency lockfiles. Run longer experiments on dedicated hardware for capacity planning; a short loopback experiment is a regression check, not a throughput guarantee.

## PostgreSQL crash and restore

Install each package's PostgreSQL extras before running this gate. With Docker running:

```sh
python3 tests/interop/durable.py --package-tests --active \
  --logs /tmp/a2alite-durable-logs --output /tmp/a2alite-durable.json
```

The runner creates a PostgreSQL 17 container bound to localhost, then separate disposable databases for each language. It writes a Task and encrypted callback configuration through replica A, reads them through replica B, kills A without shutdown hooks, restarts a fresh process, and uses `pg_dump`/`pg_restore` to restore into a different database. The restored service must decrypt the callback token, preserve the task ID and reject another principal. The fixed fixture encryption key is a public test key; production backups need separately managed keys.

`--active` also starts an ordinary long-running skill on A, subscribes and cancels through B, and verifies that both streams terminate with cancellation. It kills A during another task and requires B to mark the interrupted ordinary skill as failed within the recovery timeout (60 seconds by default). It does not claim that an arbitrary interrupted function resumes. `--package-tests` runs each language's PostgreSQL contracts, including atomic delivery and stale-worker fencing, against its disposable database.

Containers and databases created by the runner are removed even after a failed gate. `--container NAME` reuses an existing instance labeled `a2alite.test=contract` or `a2alite.test=production-path`; only new gate databases are removed in that mode. `--logs` retains fixture output for diagnosis; these fixtures use public test credentials only.

## Fixture contract

Each package has an executable fixture accepting `server --port N` and `client --url URL`. Servers print `A2A_LITE_READY` and clients print one `A2A_LITE_RESULT` JSON record. A client asserts its result before reporting success. The harness terminates and reaps every server it starts, including on failure.

Shared principal encodings live in [identity.json](../contracts/identity.json). Each package tests those vectors in addition to its own authorization and storage tests. Database schemas remain language-specific.
