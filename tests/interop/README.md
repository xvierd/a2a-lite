# Cross language interoperability and load gates

These gates exercise public APIs over loopback HTTP. The Lite server fixtures use disposable credentials. The independent SDK server runs entirely in memory.

## Setup

From the repository root, install the Lite development dependencies and compile the Java fixture.

```sh
uv sync --locked --project packages/python --extra dev --extra postgresql --extra sqlite
npm ci --prefix packages/typescript
packages/java/gradlew -p packages/java writeInteropClasspath
```

Use Node 20 or newer and JDK 17 or newer. Set `JAVA_HOME` if `java` does not select the required JDK. Set `A2ALITE_TEST_PYTHON` to the Lite interpreter if it differs from `packages/python/.venv/bin/python`.

The Python factory and reference server use SDK 1.3.1. The runner uses `tests/interop/.venv/bin/python` when present, falling back to the Lite interpreter. Set `A2ALITE_OFFICIAL_PYTHON` to override that choice.

```sh
uv venv --python 3.13 tests/interop/.venv
uv pip install --python tests/interop/.venv/bin/python 'a2a-sdk[http-server]==1.3.1' 'uvicorn==0.54.0'
```

## Protocol matrix

Run the PR gate from the repository root.

```sh
python3 tests/interop/run.py --output /tmp/a2alite-interop.json
```

| Direction | Cases | What must pass |
| --- | ---: | --- |
| Lite client → Lite server | 9 | Each language calls all three servers via JSON-RPC. The greeting, Task ID returned from inside the skill, remote GetTask and three ordered chunks must match. |
| Shared wire checks → Lite server | 3 | Published bindings and versions, skill tags, anonymous rejection, credential rotation, owner isolation, callback configuration IDs, SSE Task snapshot and request IDs, and failure of a real skill. |
| Official Python and JS clients → Lite server | 10 | Each public ClientFactory discovers the card from the base URL with a single enabled transport. The SDK must return the greeting, create and retrieve the same Task, and raise `TaskNotFoundError` for a missing ID. Two streams must end in `COMPLETED` after three ordered chunks and `FAILED` after a real skill failure. |

Each official client tests JSON-RPC and HTTP+JSON against the Python and TypeScript servers, and JSON-RPC against Java. The runner checks the bindings on each live card against these five combinations. A missing binding or newly advertised binding without a corresponding probe fails the PR gate.

### Extended CI or release gate

With the same setup, build the independent official Java client and run the full matrix.

```sh
packages/java/gradlew -p tests/interop/official-java installDist
python3 tests/interop/run.py --extended --output /tmp/a2alite-interop-full.json
```

The full run adds eight cases to the 22 PR cases.

- The official Java SDK 1.5.1.Final discovers each Lite card and exercises all five combinations. The fixture has a separate Gradle build and classpath.
- The three Lite clients call an independent server built with the official Python SDK's request handler, routes, task store and executor. The third text chunk comes from the terminal event. A second scenario checks discovery at a prefixed path, interface selection, two tenants and an SDK-generated streaming error after an observable chunk.

The JSON report records the Git SHA, tracked worktree state, per-case status and binding, SDK versions on successful official probes, failure diagnostics, and the reason for each omission. `success` means the selected checks passed. `fullMatrixPassed` requires all 30 cases. Counts use the status of each row. A failed check or unavailable selected server exits nonzero. The runner attempts the other selected servers after a failure.

For a focused run, `--languages python typescript` selects the Lite clients and servers. Both official factories still run against the selected servers. `--skip-protocol` runs only the selected Lite pairings. Neither a focused run nor a PR run qualifies the full matrix.

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

The runner creates a PostgreSQL 17 container bound to localhost, then separate disposable databases for each language. It writes a Task and encrypted callback configuration through replica A, reads them through replica B, kills A without shutdown hooks, restarts a fresh process, and uses `pg_dump`/`pg_restore` to restore into a different database. It also pauses a task for input on A and continues it on B after A dies, using the owner's rotated credential and preserving the original ID; another principal must be rejected. The restored service must decrypt the callback token, preserve the task ID and reject another principal. The fixed fixture encryption key is a public test key; production backups need separately managed keys.

`--active` also starts an ordinary long-running skill on A, subscribes and cancels through B, and verifies that both streams terminate with cancellation. It kills A during another task and requires B to mark the interrupted ordinary skill as failed within the recovery timeout (60 seconds by default). It does not claim that an arbitrary interrupted function resumes. `--package-tests` runs each language's PostgreSQL contracts, including atomic delivery and stale-worker fencing, against its disposable database.

Containers and databases created by the runner are removed even after a failed gate. `--container NAME` reuses an existing instance labeled `a2alite.test=contract` or `a2alite.test=production-path`; only new gate databases are removed in that mode. `--logs` retains fixture output for diagnosis; these fixtures use public test credentials only.

## Fixture contract

Each package has an executable fixture accepting `server --port N` and `client --url URL`. Servers print `A2A_LITE_READY` and clients print one `A2A_LITE_RESULT` JSON record. A client asserts its result before reporting success. The harness terminates and reaps every server it starts, including on failure.

Shared principal encodings live in [identity.json](../contracts/identity.json). Each package tests those vectors in addition to its own authorization and storage tests. Database schemas remain language-specific.
