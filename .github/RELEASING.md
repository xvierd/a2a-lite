# Publishing A2A Lite

Python and npm 1.2.0 are published and verified; Java 1.2.0 publication is pending Maven Central/signing credentials. The [release evidence](../tests/evidence/2026-10-17-1.2.0/README.md#published-release-verification) records the validated commit, builds and registry checks.

## Active workflows

The files in `.github/workflows` are authoritative. All three currently default manual `dry_run` to **false**: always pass `dry_run=true` explicitly for validation. Active workflows also publish on a published GitHub Release event as well as matching tag pushes. Choose a single publication trigger; creating release notes as a GitHub Release can otherwise attempt to publish an existing version again.

The replacements in [workflow-drafts](workflow-drafts/README.md) are inactive until a credential with GitHub workflow write permission delivers them. Their safer defaults, tag/version checks, Java signing preflight and extra integration jobs are not active checks.

Run CI against the release commit before publishing. Package versions are independent of the A2A protocol version: keep `A2A-Version: 1.0` when changing a package version.

## Java prerequisites

Actual Maven Central publication uses these repository Actions secrets:

| Secret | Value |
|---|---|
| `MAVEN_CENTRAL_USERNAME` | Username generated for a Central Portal user token |
| `MAVEN_CENTRAL_PASSWORD` | Password generated for that user token |
| `GPG_PRIVATE_KEY` | Complete ASCII-armored private signing key, with real newlines |
| `GPG_KEY_PASSWORD` | Key passphrase, if the key is encrypted |
| `GPG_KEY_ID` | Optional signing key ID |

The Maven credentials are Central Portal token credentials. The namespace `io.github.xvierd` must be verified and the signing public key published. See [Central publishing](https://central.sonatype.org/publish/publish-portal-maven/) and the [Gradle signing configuration](https://vanniktech.github.io/gradle-maven-publish-plugin/central/#in-memory-gpg-key).

Configure secrets directly in GitHub Actions settings or pipe them from the credential manager to `gh secret set`. Keep values out of source files, logs, issue bodies and chat. `GPG_PRIVATE_KEY` must contain actual armor with real newlines. The prepared Java workflow adds an explicit key preflight; the active workflow passes the key directly to Gradle.

## Validation without publication

Manually dispatch a publishing workflow with **`dry_run=true`** on the intended ref:

- Python builds wheel/sdist and uploads `python-dist`; publication is skipped.
- npm installs dependencies, runs tests and builds; publication is skipped.
- The active Java dry run runs tests and skips the publish/sign step. It does not build/upload the complete Maven distribution.

To validate the unsigned Java distribution locally, from `packages/java` with JDK 17+:

```sh
./gradlew test compileExamples --no-daemon
./gradlew jar sourcesJar javadocJar generatePomFileForMavenPublication generateMetadataFileForMavenPublication --no-daemon
```

These tasks need no signing credentials and do not publish. After the prepared Java workflow is activated, its explicit dry run also builds and retains the unsigned distribution.

## Publication

After CI and distribution validation, confirm the registry does not already contain the intended version. Use one publishing trigger per package:

- Manually dispatch the relevant workflow on the validated ref with `dry_run=false`, or
- Push `v<version>` for all packages, or a package-specific tag (`python/v<version>`, `npm/v<version>`, `java/v<version>`).

With the active workflows, check tag/package consistency manually and account for the additional GitHub Release trigger. Check the workflow result, then verify a fresh registry installation and artifact provenance before reporting completion. Registry visibility can lag a successful upload; retry read-only verification rather than submitting a duplicate publication.

Once all four prepared workflows are activated and validated, manual runs default to dry runs, tags are checked against package versions, and publishing GitHub Release notes no longer triggers a second publication. Keep this guide aligned with the active files when making that switch.
