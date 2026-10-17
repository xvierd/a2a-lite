# A2A SDK upgrade and audit follow-ups

Scope: finish the six findings from the 2026-10-17 SDK maintenance review, verify the result, and prepare the GitHub/release handoff. Future roadmap features outside these findings are separate work.

- [x] Verify latest stable SDKs and protocol; upgrade Python, TypeScript and Java.
- [x] Secure push configuration and delivery across all three languages (authentication, task ownership, configuration IDs and callback URLs).
- [x] Complete Java standalone streaming/task operations and protocol/JSON-RPC validation.
- [x] Select compatible discovery interfaces and propagate authenticated TypeScript principals into SDK operations.
- [x] Close Python gRPC resources and align REST error media types.
- [x] Repair and validate Java release workflow; check signing prerequisites without exposing credentials.
- [x] Update migration documentation and audit results.
- [x] Run package suites, builds, lint/format/type checks and an independent review.
- [x] Commit focused changes, push a branch, and verify GitHub CI.
- [ ] Finish publication when release credentials are available.

## External dependency

GitHub repository secret names currently include only `NPM_TOKEN`; the Java workflow references Maven Central credentials and GPG signing secrets that are absent. No local secret signing key was listed. Requested the credential location/configuration from the user; code work continues independently.

## Verified locally

- Python: 643 passed, one Docker opt-in skip; 91.33% coverage. Full CI lint/format, example compilation and 1.1.0 wheel/sdist builds passed. Independent focused review: 73 tests passed.
- TypeScript: 339 passed across 21 suites; 84.83% line coverage. Typecheck, build, format, lint and persistence example passed (16 existing lint warnings). Package 1.1.0 import/app smoke passed.
- Release workflows: YAML parsed and every shell step passed `bash -n`. Java credential preflight rejects missing/malformed keys and accepts a disposable test key without exposing credentials.
- Cross-language smoke: authenticated calls and SSE streams passed in both Python↔TypeScript directions; unauthenticated calls returned 401 and discovery selected JSON-RPC when listed after HTTP+JSON. Temporary servers and files only.
- Java: 223 tests passed, `compileExamples` passed, all eight standalone Lite example builds passed against composite 1.1.0. SSE regressions cover normal completion, failure, unknown skill and middleware failure.
- Signing smoke: `signMavenPublication` produced six artifacts signed with a disposable local key; GPG verified every signature. The key and test signatures were deleted. Nothing was published by this check.

## GitHub delivery constraint

The HTTPS credential can push package code but GitHub rejects workflow changes because it lacks the `workflow` scope. The configured SSH agent (1Password) failed to sign. All four prepared workflow changes remain preserved in local branch `codex/a2a-sdk-upgrade-and-hardening` at `5021344`; branch `codex/a2a-runtime-upgrade` delivers the package changes and documentation with the existing CI definitions. Enabling the GitHub permission or authorizing SSH is required to deliver the workflow improvements.

## Remote verification

- [PR #5](https://github.com/xvierd/a2a-lite/pull/5) was merged on 2026-10-17 at `4d9e655`. [Main CI](https://github.com/xvierd/a2a-lite/actions/runs/39066109738) passed in all seven environments.
- [CI](https://github.com/xvierd/a2a-lite/actions/runs/39064570880) passed on source commit `ff3b38f`: Python 3.10/3.11/3.12, Node 20/22 and Java 17/21.
- [Python dry run](https://github.com/xvierd/a2a-lite/actions/runs/39064641530) and [npm dry run](https://github.com/xvierd/a2a-lite/actions/runs/39064643732) passed; publication was skipped.
- The authorized 1.1.0 [Python publication](https://github.com/xvierd/a2a-lite/actions/runs/39066410666) and [npm publication](https://github.com/xvierd/a2a-lite/actions/runs/39066412902) succeeded from that merge commit. Clean registry installations, CLI and HTTP quickstarts passed; PyPI wheel/sdist hashes match the published build artifacts and npm provenance is available. Java publication and workflow delivery still require the prerequisites above.

## Learning to production: 1.2.0 implementation

Approved on 2026-10-17. See [ROADMAP.md](../ROADMAP.md#learning-to-production-improvement-plan--2026-10-17) for the original acceptance criteria and [OPERATIONS.md](../OPERATIONS.md) for supported behavior and limits.

- [x] Add progressive examples, real protocol task IDs, scoped identities and rotating client credentials in all three languages.
- [x] Add managed lifecycle, bounded admission/output/history, graceful shutdown and health diagnostics.
- [x] Implement durable state, ownership, schema setup, encrypted callback configuration, rotation and retention.
- [x] Implement atomic callback handoff, bounded retry/replay and stable delivery IDs for receiver deduplication.
- [x] Implement and exercise two-replica subscription/cancellation, stale-writer fencing and explicit crash reconciliation; document language-specific checkpoint contracts.
- [x] Add nine-pair interoperability, official SDK, PostgreSQL crash/restore, package contracts and local load runners.
- [x] Write migration and operator guides; compile and run the progressive examples.
- [x] Record final integrated qualification on frozen source: all nine language pairs, three official-SDK profiles, all PostgreSQL failure/restore profiles and 12,000 local load requests pass. See [evidence](../tests/evidence/2026-10-17-1.2.0/README.md).
- [x] Publish 1.2.0 Python/npm from validated merge `7ef5ccc` and verify clean registry installations, PyPI artifact hashes and npm signatures/provenance.
- [ ] Activate expanded CI/release workflows when GitHub workflow permission is available.
- [ ] Publish Java when Maven Central and signing prerequisites are available.
- [ ] Qualify an agreed production workload and hardware profile against latency, availability, RPO and RTO targets; include long-duration SSE/callback-outage and network-failure campaigns.
- [ ] Validate the learning sequence with a person unfamiliar with the project.

### Package evidence before integrated release gates

- Python: 685 tests pass without the PostgreSQL opt-in (14 skipped), 89.32% coverage; 28 SQLite/PostgreSQL persistence/recovery cases pass. Lint, format, wheel/sdist and clean installation pass.
- TypeScript: 451 pass without PostgreSQL (17 skipped); default coverage 81.67% statements, 72.29% branches, 81.38% functions and 83.08% lines. With PostgreSQL, 468 pass. Typecheck/build/format pass; lint has zero errors and 16 existing warnings. Clean package Message/Task/SSE/credential-rotation checks pass.
- Java: 248 pass with PostgreSQL, including 13 PostgreSQL cases; `compileExamples`, nine Lite builds and six Maven builds pass. Learning and authenticated examples run successfully.
- Independent reviews fixed stale-producer cancellation, cross-replica terminal-stream races, deadline/output limits, paused-task continuation and revoked-subscription replay.

Coordination adapters are opt-in references, not a certification. Arbitrary interrupted functions do not resume automatically, cancellation remains cooperative, and external effects need application idempotency. Workflow drafts are reviewable files, not active checks.

## 1.2.0 remote delivery

- [PR #6](https://github.com/xvierd/a2a-lite/pull/6) merged on 2026-10-17 at `7ef5ccc73d3cf1b75773d40579c7c78001ff73c3`.
- [PR CI](https://github.com/xvierd/a2a-lite/actions/runs/39070418470) and [merge CI](https://github.com/xvierd/a2a-lite/actions/runs/39070566956) passed all seven environments: Python 3.10/3.11/3.12, Node 20/22 and Java 17/21.
- [Python dry run](https://github.com/xvierd/a2a-lite/actions/runs/39070451741) and [npm dry run](https://github.com/xvierd/a2a-lite/actions/runs/39070453562) passed without publication.
- [Python publication](https://github.com/xvierd/a2a-lite/actions/runs/39070676912) and [npm publication](https://github.com/xvierd/a2a-lite/actions/runs/39070678731) succeeded from that exact merge. Clean installations from both public registries passed CLI/import and authenticated Message/Task/stream checks. Python also passed durable restart and credential rotation; npm passed rotated task ownership and rejected anonymous calls. [Python release evidence](../tests/evidence/2026-10-17-1.2.0/python-release.json) confirms exact wheel/sdist hashes against the workflow artifact; [npm release evidence](../tests/evidence/2026-10-17-1.2.0/npm-release.json) confirms tarball integrity, signatures and provenance for the merge commit.
- Java 1.2.0 library, sources, Javadoc, POM and Gradle metadata were generated and inspected locally. POM/metadata carry Jetty core/EE10 12.1.14 and Jackson 2.22.3 platform alignment. Java has not been published.
- Fresh access checks still show no GitHub `workflow` scope and no Maven Central/GPG repository secrets. Workflow drafts remain inactive; these are external prerequisites, not failed package tests.

## Post-release documentation alignment

- [x] Align the Spanish README, assistant reference and language/example guides with 1.2.0 behavior and the actual publication status.
- [x] Check changed snippets, local links and release instructions; keep this documentation correction separate from package publication.

Validation: local links across all 62 tracked Markdown files; Python constructor signatures and affected snippets, including sync/async test clients and stable authentication; 23 TypeScript snippets under strict type checking plus the executable learning path; Java shell/JSON examples, SSE reader and Gradle task resolution. `git diff --check` passes. This pass changes Markdown only; PyPI/npm remain 1.2.0 and Java publication remains pending.
