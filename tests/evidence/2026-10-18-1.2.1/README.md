# Python/npm 1.2.1 documentation release

Published on 2026-10-18 from commit `1e1131b9dee4f16b6993b40d55ed0612f3af17d9`, merged through [PR #9](https://github.com/xvierd/a2a-lite/pull/9).

This patch puts the corrected README examples and absolute documentation links on PyPI and npm. Runtime behavior, dependency requirements and the npm lock dependency graph are unchanged from 1.2.0; source changes outside Markdown are package and CLI version strings. Java remains at source version 1.2.0 and has not been published to Maven Central.

## Validation and publication

- [PR CI](https://github.com/xvierd/a2a-lite/actions/runs/39094079832) and [main CI](https://github.com/xvierd/a2a-lite/actions/runs/39094185451) passed in all seven environments: Python 3.10/3.11/3.12, Node 20/22 and Java 17/21.
- Local wheel/sdist and npm tarball builds included the updated READMEs. Isolated artifact installations, CLI versions, imports and focused Message/Task/stream checks passed.
- [PyPI publication](https://github.com/xvierd/a2a-lite/actions/runs/39094204688) and [npm publication](https://github.com/xvierd/a2a-lite/actions/runs/39094211458) each ran once from that commit through manual dispatch. No release event or tag was created.

## Public registry verification

- [Python evidence](python-release.json): registry README matches the source exactly; wheel and sdist SHA256 values match both registry metadata and the workflow artifacts. A fresh installation from PyPI passed version, CLI, Message, real Task ID, authenticated call and streaming checks.
- [npm evidence](npm-release.json): latest version and package README, tarball integrity and README, clean registry installation, ESM/CJS/CLI smoke and signed provenance were checked against the release commit.
- npm initially returned 404 while processing the accepted publication. Verification waited for public availability without submitting another publication.

The earlier [1.2.0 runtime qualification](../2026-10-17-1.2.0/README.md) remains the source for interoperability, PostgreSQL failure/restore and local load results; this documentation patch does not claim a new production workload qualification.
