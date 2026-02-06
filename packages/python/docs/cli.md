# CLI Reference

A2A Lite includes a command-line tool for scaffolding, testing, and inspecting agents.

## Installation

The CLI is installed automatically with `pip install a2a-lite`.

```bash
a2a-lite --help
```

## Commands

### `init` — Create a New Project

Scaffolds a complete agent project with tests and configuration.

```bash
a2a-lite init my-agent
a2a-lite init my-agent --path /custom/path
```

**Generated files:**

- `agent.py` — Agent with two example skills
- `pyproject.toml` — Project dependencies
- `README.md` — Getting started guide
- `tests/test_agent.py` — Unit tests
- `.gitignore` — Python gitignore

### `inspect` — View Agent Card

Fetch and display an agent's capabilities.

```bash
a2a-lite inspect http://localhost:8787
```

Shows a formatted table with the agent's name, version, description, skills, and capabilities.

### `test` — Test a Skill

Send a request to a running agent and display the response.

```bash
a2a-lite test http://localhost:8787 greet -p name=World
a2a-lite test http://localhost:8787 calc -p a=2 -p b=3

# Raw JSON output
a2a-lite test http://localhost:8787 greet -p name=World --json
```

**Options:**

- `-p, --param KEY=VALUE` — Skill parameters (repeatable)
- `-j, --json` — Output raw JSON instead of formatted

### `discover` — Compare Multiple Agents

Discover and compare multiple agents side by side.

```bash
a2a-lite discover http://localhost:8787 http://localhost:8788
```

Shows a table with each agent's name, URL, version, skill count, and capabilities.

### `serve` — Run an Agent File

Run an agent from a Python file without the `if __name__` boilerplate.

```bash
a2a-lite serve agent.py
a2a-lite serve agent.py --port 9000
```

The file must define an `agent` variable of type `Agent`.

### `version` — Show Version

```bash
a2a-lite version
```
