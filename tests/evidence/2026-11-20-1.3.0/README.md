# A2A Lite 1.3.0 release qualification

Release date in Argentina was November 20, 2026 (November 21 UTC). [Source commit `e86e340`](https://github.com/xvierd/a2a-lite/commit/e86e340b0fe1386e0e23e9b1e65ee93c529adb0c) contains the implementation and CI harness used to build the PyPI and npm packages. Java was qualified from source on JDK 17 and 21.

## Package and interoperability results

| Check | Result |
|---|---|
| Local package suites with Docker and PostgreSQL | Python 761, TypeScript 519, Java 272. All 1,552 passed with zero skips. Python coverage was 90.67% with branch measurement enabled. TypeScript line coverage was 90.10%. |
| GitHub package CI | Python 3.10 with SDK 1.2.2, Python 3.11 and 3.12 with SDK 1.3.1, Node 20 and 22 with SDK 1.3.0, JDK 17 and 21 with SDK 1.5.1.Final. All seven passed. [CI run](https://github.com/xvierd/a2a-lite/actions/runs/44842022765) |
| Public client/server compatibility | All 30 cases passed. They include the nine Lite pairs, the official Python, JS and Java clients on all five advertised server/binding combinations, the reverse direction against an independent SDK server, and the three shared wire profiles. [Case results](interop.json) |
| Google ADK 2.15.0 | 35 cases passed with the official A2A Python SDK 1.3.1, including session reload and streamed artifact completion. The basic greetings did not carry an ADK extension header in either configured mode. [Cases](consumers.json) |
| A2A TCK at `5e6f37c` | 62 upstream cases passed across eight fixtures/profiles. They cover public cards and selected authenticated JSON-RPC/HTTP+JSON operations. [Profile counts](consumers.json) · [Test selection and limits](../../qualification/README.md) |
| PostgreSQL 17 | Two replicas, process termination, restart, backup/restore, ownership checks, remote cancellation and interrupted-task reconciliation passed in each language. [Per-language results](durable.json) |
| Dependency checks | Local pip-audit and npm audit reported zero known vulnerabilities in the dependency sets examined. The OSV check found no matching advisories for the 86 resolved Java test-runtime dependencies at review time. |

[GitHub interoperability and recovery](https://github.com/xvierd/a2a-lite/actions/runs/44842022252) · [Python packaging dry run](https://github.com/xvierd/a2a-lite/actions/runs/44842041944) · [npm packaging dry run](https://github.com/xvierd/a2a-lite/actions/runs/44842048068).

## Published distributions

The [PyPI release](https://pypi.org/project/a2a-lite/1.3.0/) and [npm release](https://www.npmjs.com/package/a2a-lite/v/1.3.0) each ran once from their respective package tag. See the [Python publication](https://github.com/xvierd/a2a-lite/actions/runs/44844274277), [npm publication](https://github.com/xvierd/a2a-lite/actions/runs/44844273343) and [GitHub release](https://github.com/xvierd/a2a-lite/releases/tag/python/v1.3.0).

The [registry verification](registry.json) compared the wheel and sdist SHA-256 and npm tarball SHA-512 against registry metadata, public downloads and GitHub artifacts. The npm SLSA statement identifies the release commit and workflow. A fresh install from each registry passed the CLI and message/task/stream checks. JavaScript passed both ESM and CommonJS imports and npm signature verification. Both registries listed 1.3.0 as their latest version after propagation. Maven Central publication was excluded.
