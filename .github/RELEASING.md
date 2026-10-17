# Publishing A2A Lite

> The workflow improvements described below are preserved in [workflow-drafts](workflow-drafts/README.md), pending a GitHub credential authorized to update `.github/workflows`. Those drafts are not active. Until applied, pass `dry_run=true` explicitly and do not rely on the new preflight, integration jobs or tag/version checks.

Run CI against the release commit before publishing. Package versions are independent of the A2A protocol version: keep `A2A-Version: 1.0` even when the package version changes.

## Java prerequisites

The Maven Central workflow uses these repository Actions secrets:

| Secret | Value |
|---|---|
| `MAVEN_CENTRAL_USERNAME` | Username generated for a Central Portal user token |
| `MAVEN_CENTRAL_PASSWORD` | Password generated for that user token |
| `GPG_PRIVATE_KEY` | Complete ASCII-armored private signing key, with real newlines |
| `GPG_KEY_PASSWORD` | Key passphrase, if the key is encrypted |
| `GPG_KEY_ID` | Optional signing key ID |

The Maven username/password are token credentials, not the account login. The namespace `io.github.xvierd` must be verified in Central Portal and the signing public key must be published. See the [Central publishing documentation](https://central.sonatype.org/publish/publish-portal-maven/) and the [Gradle plugin signing configuration](https://vanniktech.github.io/gradle-maven-publish-plugin/central/#in-memory-gpg-key).

Configure secret values directly in GitHub Actions settings or pipe them from the credential manager to `gh secret set`; never put them in source files, logs, issue bodies, or chat. `GPG_PRIVATE_KEY` must not contain literal `\n` escape sequences or a base64 encoding of the armor. The workflow checks missing secrets and armor boundaries before invoking signing; Gradle verifies that the key and passphrase can actually sign.

## Validation without publication

Run **Publish Java to Maven Central** with `dry_run=true`. This is the default for manual runs. It executes tests, compiles examples, builds the library/source/Javadoc jars and POM, and uploads `java-dist`. No signing credentials are needed and nothing is published.

The Python and npm workflows also default to `dry_run=true` on manual runs. Use it to validate their distribution builds without publishing.

## Publication

After validation and version changes, use exactly one publishing trigger per package:

- Push `v<version>` to publish all packages, or a package-specific tag (`python/v<version>`, `npm/v<version>`, `java/v<version>`).
- Alternatively, manually run the relevant publishing workflow on the validated commit with `dry_run=false`.

The workflows publish on tag pushes or explicit manual requests. Tag-triggered runs verify that the tag matches the package version. Creating GitHub Release notes for an existing tag does not schedule a second publication. Check each workflow's result and the package registry before reporting success. A missing Java signing key blocks Java publication but does not prevent a dry run.
