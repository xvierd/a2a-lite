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

- [PR #5](https://github.com/xvierd/a2a-lite/pull/5) contains the package and documentation changes.
- [CI](https://github.com/xvierd/a2a-lite/actions/runs/39064570880) passed on source commit `ff3b38f`: Python 3.10/3.11/3.12, Node 20/22 and Java 17/21.
- [Python dry run](https://github.com/xvierd/a2a-lite/actions/runs/39064641530) and [npm dry run](https://github.com/xvierd/a2a-lite/actions/runs/39064643732) passed; publication was skipped.
- Release 1.1.0 is prepared; no package was published by this work. Remaining workflow-permission and Java-credential requirements are above.
