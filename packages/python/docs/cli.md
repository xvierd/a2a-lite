# CLI Reference

A2A Lite ships a command-line tool for scaffolding, serving, testing, and inspecting agents that speak **A2A protocol v1.0**.

## Installation

The CLI is installed with the Python package:

```bash
pip install a2a-lite
# or, from this monorepo:
pip install -e packages/python

a2a-lite --help
a2a-lite <command> --help   # details for one command
```

Entry point: `a2a-lite` (module: `a2a_lite.cli`).

## Command overview

| Command | Purpose |
|---------|---------|
| [`init`](#init--scaffold-a-basic-project) | Scaffold a basic agent project |
| [`create`](#create--full-project-with-docker) | Full project + tests + Docker |
| [`serve`](#serve--run-an-agent-file) | Run an agent from a `.py` file |
| [`inspect`](#inspect--rich-agent-card) | Rich agent-card table (skills, capabilities) |
| [`info`](#info--compact-agent-info) | Compact plain-text agent info |
| [`test`](#test--call-a-skill) | Call a skill on a running agent |
| [`discover`](#discover--compare-several-agents) | Compare several agent URLs side by side |
| [`doctor`](#doctor--environment--protocol-check) | Local env + optional remote v1.0 check |
| [`version`](#version) | Print package version |

> **TypeScript:** `npx a2a-lite` provides `init`, `inspect`, `info`, `test`, `discover`, and `doctor` (no `create` / `serve`). See [`packages/typescript/README.md`](../../typescript/README.md#cli).

---

## `init` — Scaffold a basic project

Creates a directory with a minimal agent, tests, and config.

```bash
a2a-lite init my-agent
a2a-lite init my-agent --path /custom/path
```

| Argument / option | Description |
|-------------------|-------------|
| `NAME` | Project name (required) |
| `--path PATH` | Directory to create the project in (default: `./NAME`) |

**Generated files:**

- `agent.py` — Agent with example skills (`hello`, `echo`)
- `pyproject.toml` — Dependencies (`a2a-lite>=1.0.0`)
- `README.md` — Getting started
- `tests/test_agent.py` — Unit tests with `AgentTestClient`
- `.gitignore` — Python ignores

---

## `create` — Full project with Docker

Like `init`, but also generates **Dockerfile**, **docker-compose.yml**, and (when the CLI runs from a local a2a-lite checkout) a **vendored** copy of the library so `docker build` works before 1.0 is on PyPI.

```bash
a2a-lite create my-agent
a2a-lite create my-agent --path /tmp/my-agent
```

| Argument / option | Description |
|-------------------|-------------|
| `NAME` | Project name (required) |
| `--path PATH` | Directory to create the project in |

**Generated files (in addition to `init`):**

- `Dockerfile` — `python:3.12-slim`, installs a2a-lite, exposes `8787`
- `docker-compose.yml` — maps `8787:8787`
- `vendor/a2a-lite/` — only when the CLI can locate a local package source

```bash
cd my-agent
uv run pytest tests/
uv run agent.py
# or: a2a-lite serve agent.py
docker compose up --build
a2a-lite doctor http://localhost:8787
```

---

## `serve` — Run an agent file

Starts the agent without requiring an `if __name__ == "__main__"` block.

```bash
a2a-lite serve agent.py
a2a-lite serve agent.py --port 9000
```

| Argument / option | Description |
|-------------------|-------------|
| `FILE` | Python file that defines an `agent` variable of type `Agent` (required) |
| `--port INTEGER` | Listen port (default: `8787`) |

The file must expose a top-level `agent` instance:

```python
from a2a_lite import Agent

agent = Agent(name="Demo", description="…")

@agent.skill("hello")
async def hello(name: str = "World") -> str:
    return f"Hello, {name}!"
```

---

## `inspect` — Rich agent card

Fetches `/.well-known/agent-card.json` and prints a formatted view (name, version, description, skills, capabilities, interfaces).

```bash
a2a-lite inspect http://localhost:8787
```

| Argument | Description |
|----------|-------------|
| `URL` | Base URL of the agent (required) |

Rejects **A2A 0.3** cards with a clear error (a2a-lite 1.0 requires protocol v1.0).

---

## `info` — Compact agent info

Same card fetch as `inspect`, but plain-text and compact (good for scripts and quick checks).

```bash
a2a-lite info http://localhost:8787
```

| Argument | Description |
|----------|-------------|
| `URL` | Base URL of the agent (required) |

---

## `test` — Call a skill

Sends a JSON-RPC **`SendMessage`** request (A2A v1.0, header `A2A-Version: 1.0`) using the lite payload convention:

`{"skill": "<name>", "params": {…}}` inside a text part.

```bash
a2a-lite test http://localhost:8787 greet -p name=World
a2a-lite test http://localhost:8787 calc -p a=2 -p b=3

# Raw JSON response body
a2a-lite test http://localhost:8787 greet -p name=World --json

# Battleship example (if agent.py is on :8790)
a2a-lite test http://localhost:8790 status
a2a-lite test http://localhost:8790 receive_shot -p row=3 -p col=4
a2a-lite test http://localhost:8790 next_shot
```

| Argument / option | Description |
|-------------------|-------------|
| `URL` | Agent base URL (required) |
| `SKILL` | Skill id / name (required) |
| `-p, --param KEY=VALUE` | Skill parameters (repeatable) |
| `-j, --json` | Print raw JSON instead of the formatted result |

Values after `=` are kept as strings unless they look like numbers/booleans; prefer multiple `-p` flags over a single JSON blob.

---

## `discover` — Compare several agents

Fetches each agent card and shows a comparison table (name, URL, version, skill count, capabilities).

```bash
a2a-lite discover http://localhost:8787 http://localhost:8788
a2a-lite discover http://127.0.0.1:8791 http://127.0.0.1:8792
```

| Argument | Description |
|----------|-------------|
| `URLS…` | One or more agent base URLs (required) |

> There is **no mDNS scan** in the current CLI: every URL must be passed explicitly. Older docs that said `a2a-lite discover` with no args were incorrect.

---

## `doctor` — Environment + protocol check

Diagnoses the **local** install and, optionally, a **remote** agent.

```bash
a2a-lite doctor
a2a-lite doctor http://localhost:8787
```

| Argument | Description |
|----------|-------------|
| `URL` | Optional agent URL to verify |

**Local checks:**

- Versions: `a2a-lite`, `a2a-sdk`, Python
- SDK range: `a2a-sdk >= 1.1.2, < 2.0`
- Features: JSON-RPC, REST, gRPC (if `a2a-lite[grpc]` / `grpc` installed)
- Optional extras: `mcp`, `openai`, `anthropic`, `bedrock` (`boto3`), `oauth` (`jwt`)

**Remote checks (when `URL` is given):**

- Fetches the agent card
- Confirms A2A **v1.0** shape (`supportedInterfaces`; rejects 0.3 cards)
- Summarizes name, skills, and advertised interfaces

Exit status is non-zero when the environment or the remote agent fails the checks.

---

## `version`

```bash
a2a-lite version
```

Prints the installed a2a-lite version string.

---

## Typical workflows

### New agent from zero

```bash
a2a-lite create greeter
cd greeter
a2a-lite serve agent.py
# other terminal:
a2a-lite doctor http://localhost:8787
a2a-lite test http://localhost:8787 hello -p name=A2A
```

### Smoke-test any A2A v1.0 agent

```bash
a2a-lite inspect http://localhost:8790
a2a-lite info http://localhost:8790
a2a-lite test http://localhost:8790 status
```

### Compare two agents (e.g. battleship arena)

```bash
a2a-lite discover http://127.0.0.1:8791 http://127.0.0.1:8792
```

---

## Protocol notes (v1.0)

- Agent card path: `GET {url}/.well-known/agent-card.json`
- Wire method for `test`: JSON-RPC **`SendMessage`** with header **`A2A-Version: 1.0`**
- Lite skill body (text part): `{"skill": "…", "params": {…}}`
- Agents still on A2A **0.3** are rejected with a migration hint (see [MIGRATION.md](../../../MIGRATION.md))

---

## Related docs

- [Getting started](index.md)
- [Examples](examples.md)
- [Multi-agent](multi-agent.md)
- Root [README CLI section](../../../README.md#cli)
