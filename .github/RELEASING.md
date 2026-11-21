# Publishing A2A Lite

The 1.3.0 release targets PyPI and npm. Java is distributed from source. Package versions are independent of the A2A wire version, which remains `1.0`. [Previous release evidence](../tests/evidence/2026-10-18-1.2.1/README.md)

## Validate a release candidate

1. Run unit CI and the full interoperability workflow on the exact main commit intended for release. Pull requests use a smaller set of interoperability checks. [CI](workflows/ci.yml) · [Interop](workflows/compatibility.yml)
2. Dispatch the selected publication workflows on that commit or its branch with `dry_run=true`. This is the default for manual publication jobs. Python builds a wheel and sdist, npm builds and packages the library, and Java can build unsigned source, Javadoc, binary and Maven artifacts for inspection.
3. Confirm the version is available for publication in each target registry. Verify the run's head SHA before moving tags or publishing from a branch.

## Publish

The active workflows publish on their package-specific tag, a shared `v<version>` tag, or an explicit manual dispatch with `dry_run=false`. Each tag must match the version in the package manifest. Use `python/v<version>` and `npm/v<version>` for a Python/npm release. A shared `v<version>` also starts the Maven workflow. GitHub Release notes can be attached to an existing package tag without triggering another upload.

Choose one publishing trigger per registry. After the job succeeds, verify a fresh registry installation, the published artifact hashes and provenance against the validated commit. If the new version takes time to appear in a registry, recheck the registry and the original job before retrying an upload.

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

Configure secrets directly in GitHub Actions settings or pipe them from the credential manager to `gh secret set`. Keep values out of source files, logs, issue bodies and chat. `GPG_PRIVATE_KEY` must contain actual armor with real newlines. The Java workflow checks for the required credentials before starting a publication.
