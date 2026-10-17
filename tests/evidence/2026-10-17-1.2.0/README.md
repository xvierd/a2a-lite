# A2A Lite 1.2.0 local qualification evidence

Checked 2026-10-17. These are reproducible local observations, not an enterprise certification or production SLO.

## Source and environment

- Protocol and PostgreSQL gates: clean tracked source `0305da618fa0e75bd31f890bd5ade4e708d247d1`.
- Load gate: clean tracked source `c36cd5a0c08519a54277db06bfb4d9f92351b635`. Intervening changes corrected documentation and merged the unchanged main baseline; runtime code is identical.
- macOS 26.6.2, ARM, 11 logical CPUs; Python 3.13.9, Node 25.8.2, GraalVM Java 21.0.2. This local run does not establish support for every runtime version in CI.
- PostgreSQL 17.11 in a disposable Docker instance bound to localhost. Independent databases per implementation.
- SDK baseline: Python 1.2.2, TypeScript 1.3.0, Java 1.4.0.Final; A2A wire protocol 1.0.

## Results

- [Interoperability](interop.json): all nine Lite client/server pairs pass Message, Task, real Task ID/GetTask and ordered streaming. Shared protocol checks cover authenticated ownership, credential rotation, callback configuration IDs, failures and initial SSE snapshots. Official Python SDK 1.2.2 independently passes against all three servers.
- [Durability](durable.json): all three pass two-replica reads, pause/continuation with owner isolation, process kill/restart, dump/restore, callback secret decryption, remote subscription/cancellation and stale-writer fencing. Language PostgreSQL suites also pass. Ordinary interrupted work became FAILED after approximately 30.21s (Python), 15.44s (TypeScript), and 5.33s (Java), following configured leases. These are single-run observations, not RTO guarantees.
- Package validation: Python 685 default passes with 14 PostgreSQL opt-in skips and 89.32% coverage, plus 28 SQLite/PostgreSQL contract cases; TypeScript 451 default passes/17 PostgreSQL skips and all default coverage thresholds pass, 468 passes with PostgreSQL; Java 248 passes including 13 PostgreSQL cases. Counts overlap across focused and full runs and should not be summed as unique tests.
- Build/example validation: Python wheel/sdist, TypeScript ESM/CJS/types, Java library, nine Lite examples and six Maven examples. Progressive examples run without an LLM account. Clean wheel/tarball installations pass CLI/import and local authenticated Message/Task/stream checks.
- Dependency observations: [Python installed profile](python-installed-audit.json), [npm installed profile](npm-installed-audit.json), and [86 resolved Java test-runtime dependencies](java-audit.json) have no reported known advisories at scan time. Python development and TypeScript development environments were also checked. Optional providers absent from those environments are outside this evidence.

## Local load regression

[Raw results](load.json): 1,000 requests for each of four workloads in each language, concurrency eight, five excluded warmups per workload: **12,000 requests, zero observed errors**. One authenticated memory-backed server per language over loopback; no TLS, database, LLM, remote network or callback receiver. I/O waits 20ms; streams return three chunks. Latencies cover completed requests and streams, not time to first token.

| Language | Workload | Completed/s | p95 ms | p99 ms | Error rate |
|---|---|---:|---:|---:|---:|
| python | message | 2181.2 | 4.10 | 6.32 | 0% |
| python | task | 1167.0 | 8.23 | 8.73 | 0% |
| python | io | 326.0 | 25.33 | 33.03 | 0% |
| python | stream | 565.5 | 15.39 | 17.00 | 0% |
| typescript | message | 6141.9 | 1.86 | 2.27 | 0% |
| typescript | task | 5651.6 | 1.74 | 1.96 | 0% |
| typescript | io | 297.5 | 29.83 | 31.61 | 0% |
| typescript | stream | 3492.6 | 4.16 | 5.69 | 0% |
| java | message | 3148.1 | 4.61 | 7.28 | 0% |
| java | task | 3861.3 | 3.46 | 5.54 | 0% |
| java | io | 348.5 | 24.17 | 25.09 | 0% |
| java | stream | 50.6 | 162.40 | 165.12 | 0% |

Short runs, shared desktop hardware and runtime differences make these regression observations unsuitable as capacity estimates or language rankings. Java streaming latency warrants workload-specific profiling before setting an SSE latency target.

## Remaining qualification and delivery prerequisites

- Production workload, dedicated hardware, latency/availability/RPO/RTO targets, sustained SSE fan-out, callback outage and network interruption campaigns remain to be agreed and exercised.
- The progressive learning sequence has automated execution evidence, but has not been evaluated by a new human learner.
- Database schemas are language-specific. There is no claim of mixed-language replicas sharing tables, arbitrary-function crash resumption, uncooperative-code termination, or exactly-once external side effects.
- Expanded CI/release definitions are inactive drafts until GitHub workflow write permission is available. Maven Central credentials and signing keys are required for Java publication. See [release status](../../../tasks/todo.md).

Commands and setup are documented in [the gate guide](../../interop/README.md). Deployment boundaries and recovery procedures are in [OPERATIONS.md](../../../OPERATIONS.md).

## Published release verification

[PR #6](https://github.com/xvierd/a2a-lite/pull/6) merged at `7ef5ccc73d3cf1b75773d40579c7c78001ff73c3`. [Merge CI](https://github.com/xvierd/a2a-lite/actions/runs/39070566956) passed Python 3.10/3.11/3.12, Node 20/22 and Java 17/21 before publication. Runtime sources are unchanged from the local qualification commits above.

- [PyPI 1.2.0](https://pypi.org/project/a2a-lite/1.2.0/): clean registry installation with SQLite/OAuth extras passed CLI/import, Message, real Task ID, streaming, checkpoint, restart and key rotation. [Recorded hashes](python-release.json) for the wheel and sdist exactly match the [publication build](https://github.com/xvierd/a2a-lite/actions/runs/39070676912).
- [npm 1.2.0](https://www.npmjs.com/package/a2a-lite/v/1.2.0): clean registry installation passed CLI, ESM/CJS, authenticated HTTP calls, Task reads, streams, rotated ownership and anonymous rejection. [Verification](npm-release.json) records zero audit findings, valid signatures and provenance tied to the [publication run](https://github.com/xvierd/a2a-lite/actions/runs/39070678731) and exact merge commit.
- Java artifacts (library, sources, Javadoc, POM and Gradle metadata) were generated and inspected. Publication remains pending Maven Central/signing credentials; expanded workflows remain inactive drafts.
