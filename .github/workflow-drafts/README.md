# Workflow changes awaiting activation

These four files are reviewable replacements for the matching files in
`.github/workflows`. GitHub does not execute workflows from this directory.
The current publishing credential can push package code but lacks the `workflow`
scope; GitHub rejected the earlier workflow push. Activate these changes only
through a credential authorized to update workflows.

After review, copy the four YAML files into `.github/workflows` in one commit.
Run CI on that commit and dispatch each publishing workflow with `dry_run=true`
before publishing. The Java dry run works without signing credentials; actual
publication also needs the secrets listed in [RELEASING.md](../RELEASING.md).

The CI replacement adds optional Python transports, the persistence example,
nine client/server pairings, the official SDK client, PostgreSQL package tests,
cross-replica cancellation, worker crash reconciliation and backup restoration.
Publish replacements build and retain distributions, validate tag/version
consistency and default manual runs to a dry run. Java publication validates
signing prerequisites first. Until activation, the existing workflow definitions
remain authoritative and these additional gates must be run locally.
