# External consumer and conformance qualification

Run these commands from the repository root after installing the [interop fixture dependencies](../interop/README.md#setup) and compiling Java with `writeInteropClasspath`. All servers use ephemeral loopback ports. Fixture Python defaults to `packages/python/.venv/bin/python`. Set `A2ALITE_TEST_PYTHON` to use another interpreter. Prepare the independent consumer environments before running the checks.

## PR and periodic TCK jobs

Use the TCK's own Python 3.15 environment and lockfile. The wrapper verifies the Git revision and requires a clean TCK checkout.

```sh
TCK_DIR="$(mktemp -d)"
git clone https://github.com/a2aproject/a2a-tck.git "$TCK_DIR"
git -C "$TCK_DIR" checkout --detach 5e6f37c2d38eb3d7684686243c34d365c83df49b
uv sync --project "$TCK_DIR" --python 3.15 --locked --no-dev
```

The PR job runs six upstream MUST tests against each of the three public cards.

```sh
"$TCK_DIR/.venv/bin/python" -m pytest -q tests/qualification/test_tck.py -k cards \
  --tck-checkout="$TCK_DIR" --junitxml=reports/tck-cards.xml
```

The periodic job checks the public cards and authenticated operations on the five supported server/binding combinations.

```sh
"$TCK_DIR/.venv/bin/python" -m pytest -q tests/qualification/test_tck.py \
  --tck-checkout="$TCK_DIR" --junitxml=reports/tck-periodic.xml --tck-results=reports/tck-details
```

The periodic profile includes 62 upstream test executions.

| Scope | Server fixtures | Upstream tests per fixture |
| --- | --- | --- |
| Agent card | Python, TypeScript, Java | 6 covering public discovery, required fields, schema and interface declarations. The wrapper also checks the expected bindings and protocol version. |
| JSON-RPC | Python, TypeScript, Java | 10 covering envelope/schema, JSON and SSE media types, SSE event envelopes and results, camelCase, enum serialization and missing-task Get/Cancel/Subscribe errors. |
| HTTP+JSON | Python, TypeScript | 7 covering unary response schema, success status, SSE media type, camelCase, enum serialization and missing-task Get/Cancel status codes. |

The operation profiles use the configured multiskill text route for the TCK's plain-text messages. An isolated pytest plugin supplies the disposable API key on requests to the fixture's loopback origin. Cards are retrieved anonymously. The TCK test IDs are listed in [test_tck.py](test_tck.py). The wrapper checks the upstream exit status, JUnit test count and every selected test outcome. An upstream skip, including a transport failure reported as a skip, fails the profile. Use `--tck-results=reports/tck-details` on either job to retain the upstream test names, individual outcomes and logs.

The pinned TCK also defines scenarios keyed by message ID prefixes, including task completion, input-required continuation, artifact generation, history and push delivery. These fixtures dispatch by skill or configured text entry. Those scripted scenarios, optional gRPC service, extended cards, and SHOULD/MAY requirements are outside these profiles. Java's standalone fixture advertises JSON-RPC. The non-selected SHOULD card check concerns custom binding identifiers.

## Periodic Google ADK job

Use a separate Python 3.13 environment so that installing the consumer does not change the Lite server dependencies.

```sh
ADK_ENV="$(mktemp -d)/adk"
uv venv --python 3.13 "$ADK_ENV"
uv pip install --python "$ADK_ENV/bin/python" 'google-adk[a2a]==2.15.0' 'a2a-sdk[http-server]==1.3.1' 'pytest==9.0.2'
"$ADK_ENV/bin/python" -m pytest -q tests/qualification/test_adk.py --junitxml=reports/google-adk.xml
```

ADK discovers each agent and runs in memory with no model or API account. The suite has 35 cases. Each checks both the live ADK events and the reloaded session.

- Both values of `use_legacy` exercise a unary Message and the ordered stream `one`, `two`, `three` through JSON-RPC. A failed skill must produce a failed Task and the ADK error code `A2A_TASK_FAILED` in both unary and streaming calls.
- With no configured text route, Python and TypeScript return a Message containing a structured `SkillNotFoundError` diagnostic. Java returns a failed Task with `SkillNotFoundException`. Each diagnostic must identify the available skills. With `A2ALITE_INTEROP_TEXT_ENTRY=1`, each server echoes the same free text and still dispatches an explicitly named skill.
- A separate local HTTP peer sends two updates for one artifact without a `lastChunk` field, then a completed status. ADK must emit both partials and persist one complete artifact in the session. This case exercises the Google consumer with controlled SSE bytes. The remaining cases use the Lite servers.

The ADK JUnit report records the client versions, Lite Git revision, and observed `A2A-Extensions` request header for each unary greeting. The audited version pair sent no such header in either mode against the three Lite fixtures. These mode tests exercise ADK configuration and session behavior. Extension negotiation with a peer that advertises the Google extension requires separate coverage.
