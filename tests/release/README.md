# Verify a published Python and npm release

Use the commit that passed release qualification and the run IDs of its two successful publish workflows. These commands run from the repository root on macOS or Linux. They use GitHub CLI, Python 3.12 or 3.13 with venv/pip, Node.js 20+ and an npm CLI with provenance verification. The smoke tests start servers on ephemeral loopback ports.

```sh
gh run view "$PYTHON_RUN" --repo xvierd/a2a-lite --json workflowName,headSha,conclusion
gh run view "$NPM_RUN" --repo xvierd/a2a-lite --json workflowName,headSha,conclusion
release_dir=$(mktemp -d)
gh run download "$PYTHON_RUN" --repo xvierd/a2a-lite --name python-dist --dir "$release_dir/python-dist"
gh run download "$NPM_RUN" --repo xvierd/a2a-lite --name npm-dist --dir "$release_dir/npm-dist"
python3.13 tests/release/verify.py --version "$VERSION" --commit "$SHA" \
  --python-dist "$release_dir/python-dist" --npm-dist "$release_dir/npm-dist"
```

Check both run names, their successful conclusion and their `headSha` against the intended commit. The script compares SHA-256 for the Python wheel and sdist and SHA-512 for the npm tarball across the workflow files, registry metadata and downloaded bytes. It checks the npm SLSA subject, GitHub workflow, repository and resolved Git commit. It installs the exact version from each registry in a temporary directory, confirms which artifacts were installed, runs `npm audit signatures` and exercises both CLIs, both JavaScript module formats, and message, task retrieval and streaming over HTTP in each language. A successful invocation prints a JSON report to standard output.
