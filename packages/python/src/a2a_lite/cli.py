"""
Command-line interface for A2A Lite.
"""

import asyncio
import json
import sys
from importlib import metadata as importlib_metadata
from importlib.util import find_spec
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

app = typer.Typer(
    name="a2a-lite",
    help="A2A Lite - Simplified Agent-to-Agent Protocol SDK",
    add_completion=False,
)
console = Console()

# Supported a2a-sdk range: >=1.1.2,<2.0
SDK_MIN_VERSION = (1, 1, 2)
SDK_MAX_MAJOR = 2

MIGRATION_HINT = "https://a2a-protocol.org/latest/"


def _card_url(card: dict, fallback: str) -> str:
    """Extract the agent URL from a v1.0 agent card (supportedInterfaces)."""
    interfaces = card.get("supportedInterfaces", [])
    if interfaces and isinstance(interfaces[0], dict):
        return interfaces[0].get("url", fallback)
    return fallback


def _is_v03_card(card: dict) -> bool:
    """Detect a legacy A2A 0.3 card (root url/protocolVersion, no supportedInterfaces)."""
    return "supportedInterfaces" not in card and ("url" in card or "protocolVersion" in card)


def _print_v03_panel(url: str) -> None:
    """Show a consistent, clear error when the remote agent speaks A2A 0.3."""
    console.print(
        Panel(
            f"[bold red]This agent speaks A2A 0.3 — a2a-lite 1.0 requires protocol v1.0.[/]\n\n"
            f"The agent at [cyan]{url}[/] published a legacy 0.3 agent card\n"
            f"(root [bold]url[/] + [bold]protocolVersion[/], no [bold]supportedInterfaces[/]).\n\n"
            f"[bold]What to do:[/]\n"
            f"  • Upgrade the agent to A2A v1.0.\n"
            f"  • Migration guide: [link={MIGRATION_HINT}]{MIGRATION_HINT}[/link]",
            title="Incompatible Protocol Version",
            border_style="red",
        )
    )


def _check_card_version(card: dict, url: str) -> None:
    """Reject legacy 0.3 cards with a rich error panel."""
    if _is_v03_card(card):
        _print_v03_panel(url)
        raise typer.Exit(1)


async def _fetch_card(url: str, timeout: float = 10.0) -> dict:
    """Fetch the agent card from a remote agent."""
    import httpx

    card_url = f"{url.rstrip('/')}/.well-known/agent-card.json"
    async with httpx.AsyncClient() as client:
        response = await client.get(card_url, timeout=timeout)
        response.raise_for_status()
        return response.json()


def _parse_version(version: str) -> tuple[int, ...]:
    """Parse a version string like '1.1.2' into a comparable int tuple."""
    parts = []
    for piece in version.split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _sdk_version_supported(version: str) -> bool:
    """Check an a2a-sdk version against the supported range >=1.1.2,<2.0."""
    parsed = _parse_version(version)
    return parsed >= SDK_MIN_VERSION and parsed[0] < SDK_MAX_MAJOR


@app.command()
def init(
    name: str = typer.Argument(..., help="Project name"),
    path: Path | None = typer.Option(None, help="Directory to create project in"),
):
    """
    Initialize a new A2A Lite agent project.

    Creates a new directory with a basic agent template.
    """
    project_path = path or Path(name)
    project_path.mkdir(exist_ok=True)

    # Create agent.py
    agent_template = '''"""
{name} - A2A Lite Agent

Run with: python agent.py
"""
from a2a_lite import Agent

agent = Agent(
    name="{name}",
    description="A simple A2A Lite agent",
    version="1.0.0",
)


@agent.skill("hello", description="Say hello to someone")
async def hello(name: str = "World") -> str:
    """Greets the provided name."""
    return f"Hello, {{name}}!"


@agent.skill("echo", description="Echo back the input")
async def echo(message: str) -> dict:
    """Echoes the input message."""
    return {{"received": message, "echoed": True}}


if __name__ == "__main__":
    agent.run(port=8787)
'''

    (project_path / "agent.py").write_text(agent_template.format(name=name))

    # Create pyproject.toml
    safe_name = name.lower().replace(" ", "-").replace("_", "-")
    pyproject = f'''[project]
name = "{safe_name}"
version = "0.1.0"
description = "A2A Agent: {name}"
requires-python = ">=3.10"
dependencies = [
    "a2a-lite>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]
'''
    (project_path / "pyproject.toml").write_text(pyproject)

    # Create README
    readme = f"""# {name}

An A2A Lite agent.

## Quick Start

```bash
cd {project_path}
uv run agent.py
```

## Testing

```bash
# Using the CLI
a2a-lite test http://localhost:8787 hello -p name=World

# Using pytest
uv run pytest tests/
```

## Project Structure

```
{project_path}/
  agent.py          # Agent definition and skills
  tests/
    test_agent.py   # Unit tests
  pyproject.toml    # Dependencies
  README.md         # This file
```
"""
    (project_path / "README.md").write_text(readme)

    # Create tests directory and test file
    tests_dir = project_path / "tests"
    tests_dir.mkdir(exist_ok=True)

    test_template = '''"""
Tests for {name} agent.
"""
from a2a_lite import AgentTestClient

# Import the agent from agent.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from agent import agent


client = AgentTestClient(agent)


def test_hello():
    result = client.call("hello", name="World")
    assert result == "Hello, World!"


def test_hello_custom_name():
    result = client.call("hello", name="A2A")
    assert result == "Hello, A2A!"


def test_echo():
    result = client.call("echo", message="test")
    assert result.data["received"] == "test"
    assert result.data["echoed"] is True
'''
    (tests_dir / "test_agent.py").write_text(test_template.format(name=name))

    # Create .gitignore
    gitignore = """__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
.pytest_cache/
"""
    (project_path / ".gitignore").write_text(gitignore)

    # Show result
    files_list = (
        f"  {project_path}/agent.py\n"
        f"  {project_path}/pyproject.toml\n"
        f"  {project_path}/README.md\n"
        f"  {project_path}/tests/test_agent.py\n"
        f"  {project_path}/.gitignore"
    )

    console.print(
        Panel(
            f"[green]Created project: {name}[/]\n\n"
            f"[dim]Files created:[/]\n"
            f"{files_list}\n\n"
            f"[bold]Next steps:[/]\n"
            f"  cd {project_path}\n"
            f"  uv run agent.py",
            title="A2A Lite Project Created",
            border_style="green",
        )
    )


@app.command()
def inspect(
    url: str = typer.Argument(..., help="Agent URL (e.g., http://localhost:8787)"),
):
    """
    Inspect an A2A agent's capabilities.

    Fetches and displays the agent card.
    """
    import httpx

    async def _inspect():
        card = await _fetch_card(url)
        _check_card_version(card, url)

        # Agent info panel
        agent_name = card.get("name", "Unknown")
        agent_version = card.get("version", "?")
        agent_desc = card.get("description", "-")

        console.print(
            Panel(
                f"[bold]{agent_name}[/] v{agent_version}\n\n[dim]{agent_desc}[/]",
                title="Agent Card",
                border_style="blue",
            )
        )

        # Interfaces / transports table
        interfaces = card.get("supportedInterfaces", [])
        if interfaces:
            iface_table = Table(title="Interfaces / Transports")
            iface_table.add_column("URL", style="cyan", no_wrap=True)
            iface_table.add_column("Protocol Binding", style="green")
            iface_table.add_column("Protocol Version", style="yellow")
            for iface in interfaces:
                iface_table.add_row(
                    iface.get("url", "-"),
                    iface.get("protocolBinding", "-"),
                    iface.get("protocolVersion", "-"),
                )
            console.print(iface_table)

        # Capabilities table
        capabilities = card.get("capabilities", {})
        cap_table = Table(title="Capabilities")
        cap_table.add_column("Capability", style="cyan")
        cap_table.add_column("Status", style="bold")
        cap_table.add_row(
            "Streaming",
            "[green]✅[/]" if capabilities.get("streaming") else "[red]❌[/]",
        )
        cap_table.add_row(
            "Push Notifications",
            "[green]✅[/]" if capabilities.get("pushNotifications") else "[red]❌[/]",
        )
        extensions = capabilities.get("extensions") or []
        cap_table.add_row(
            "Extensions",
            f"[green]{len(extensions)}[/]" if extensions else "[dim]none[/]",
        )
        console.print(cap_table)

        # Skills table
        table = Table(title="Skills")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("Description", style="dim")
        table.add_column("Tags", style="green")
        table.add_column("Input", style="yellow")
        table.add_column("Output", style="yellow")

        for skill in card.get("skills", []):
            input_modes = ", ".join(skill.get("inputModes", []))
            output_modes = ", ".join(skill.get("outputModes", []))
            table.add_row(
                skill.get("name", skill.get("id", "?")),
                skill.get("description", "-"),
                ", ".join(skill.get("tags", [])) or "-",
                input_modes or "-",
                output_modes or "-",
            )

        console.print(table)

        # Signatures (JWS) if present
        signatures = card.get("signatures") or []
        if signatures:
            sig_table = Table(title="Signatures")
            sig_table.add_column("#", style="dim", justify="right")
            sig_table.add_column("Protected", style="cyan")
            sig_table.add_column("Signature", style="green")
            for i, sig in enumerate(signatures, 1):
                sig_value = sig.get("signature", "")
                sig_table.add_row(
                    str(i),
                    sig.get("protected", "-"),
                    f"{sig_value[:24]}…" if len(sig_value) > 24 else sig_value or "-",
                )
            console.print(sig_table)

    try:
        asyncio.run(_inspect())
    except typer.Exit:
        raise
    except httpx.HTTPError as e:
        console.print(f"[red]Error: Could not connect to {url}[/]")
        console.print(f"[dim]{e}[/]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command()
def info(
    url: str = typer.Argument(..., help="Agent URL (e.g., http://localhost:8787)"),
):
    """
    Show agent info in a compact, readable format.

    Fetches the agent card and displays it as plain text.
    """
    import httpx

    async def _info():
        card = await _fetch_card(url)
        _check_card_version(card, url)

        agent_name = card.get("name", "Unknown")
        agent_version = card.get("version", "?")
        agent_desc = card.get("description", "-")
        agent_url = _card_url(card, url)

        typer.echo(f"Agent: {agent_name} (v{agent_version})")
        typer.echo(f"Description: {agent_desc}")
        typer.echo(f"URL: {agent_url}")

        skills = card.get("skills", [])
        if skills:
            typer.echo("")
            typer.echo("Skills:")
            for skill in skills:
                skill_name = skill.get("name", skill.get("id", "?"))
                skill_desc = skill.get("description", "-")
                typer.echo(f"  {skill_name}")
                typer.echo(f"    Description: {skill_desc}")

                input_schema = skill.get("inputSchema", {})
                properties = input_schema.get("properties", {})
                required_params = input_schema.get("required", [])

                if properties:
                    typer.echo("    Parameters:")
                    for param_name, param_info in properties.items():
                        param_type = param_info.get("type", "any")
                        req_label = "required" if param_name in required_params else "optional"
                        typer.echo(f"      {param_name} ({param_type}, {req_label})")

    try:
        asyncio.run(_info())
    except typer.Exit:
        raise
    except httpx.HTTPError as e:
        console.print(f"[red]Error: Could not connect to {url}[/]")
        console.print(f"[dim]{e}[/]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command()
def test(
    url: str = typer.Argument(..., help="Agent URL"),
    skill: str = typer.Argument(..., help="Skill name to invoke"),
    params: list[str] | None = typer.Option(None, "--param", "-p", help="Parameters as key=value pairs"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output raw JSON instead of formatted"),
):
    """
    Test an agent skill.

    Example: a2a-lite test http://localhost:8787 hello -p name=World
    """
    from uuid import uuid4

    import httpx

    # Parse parameters
    param_dict = {}
    for p in params or []:
        if "=" in p:
            key, value = p.split("=", 1)
            # Try to parse as JSON for complex types
            try:
                param_dict[key] = json.loads(value)
            except json.JSONDecodeError:
                param_dict[key] = value

    async def _test():
        async with httpx.AsyncClient() as client:
            # Detect legacy 0.3 agents before sending (fall through if the card
            # cannot be fetched; the SendMessage error will surface instead)
            try:
                card = await _fetch_card(url)
            except httpx.HTTPError:
                card = None
            if card is not None:
                _check_card_version(card, url)

            # Build request
            message = json.dumps(
                {
                    "skill": skill,
                    "params": param_dict,
                }
            )

            request_body = {
                "jsonrpc": "2.0",
                "method": "SendMessage",
                "id": uuid4().hex,
                "params": {
                    "message": {
                        "role": "ROLE_USER",
                        "parts": [{"text": message}],
                        "messageId": uuid4().hex,
                    }
                },
            }

            response = await client.post(
                url,
                json=request_body,
                headers={"A2A-Version": "1.0"},
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

            if output_json:
                # Raw JSON output
                console.print(json.dumps(result, indent=2))
            else:
                # Formatted output
                console.print("\n[bold green]Response:[/]")
                console.print_json(json.dumps(result, indent=2))

    try:
        asyncio.run(_test())
    except typer.Exit:
        raise
    except httpx.HTTPError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


@app.command()
def discover(
    urls: list[str] = typer.Argument(..., help="Agent URLs to discover"),
):
    """
    Discover and compare multiple A2A agents.

    Example: a2a-lite discover http://localhost:8787 http://localhost:8788
    """

    async def _discover():
        table = Table(title="Discovered Agents")
        table.add_column("Name", style="cyan", no_wrap=True)
        table.add_column("URL", style="dim")
        table.add_column("Version", style="green")
        table.add_column("Skills", style="yellow", justify="right")
        table.add_column("Capabilities", style="magenta")

        for url in urls:
            try:
                card = await _fetch_card(url)

                if _is_v03_card(card):
                    _print_v03_panel(url)
                    table.add_row(
                        "[red]A2A 0.3[/]",
                        url,
                        "-",
                        "-",
                        "[red]requires v1.0[/]",
                    )
                    continue

                skills_count = len(card.get("skills", []))
                caps = card.get("capabilities", {})
                cap_list = []
                if caps.get("streaming"):
                    cap_list.append("streaming")
                if caps.get("pushNotifications"):
                    cap_list.append("push")

                table.add_row(
                    card.get("name", "Unknown"),
                    _card_url(card, url),
                    card.get("version", "?"),
                    str(skills_count),
                    ", ".join(cap_list) or "-",
                )
            except Exception as e:
                table.add_row(
                    "[red]Error[/]",
                    url,
                    "-",
                    "-",
                    f"[red]{e}[/]",
                )

        console.print(table)

    asyncio.run(_discover())


@app.command()
def doctor(
    url: str | None = typer.Argument(None, help="Optional agent URL to verify"),
):
    """
    Diagnose the local environment and (optionally) a remote agent.

    Shows installed versions, transport/extra availability, and verifies
    that a remote agent speaks A2A protocol v1.0.

    Example: a2a-lite doctor http://localhost:8787
    """
    from . import __version__

    healthy = True

    # --- Versions -----------------------------------------------------------
    try:
        sdk_version: str | None = importlib_metadata.version("a2a-sdk")
    except importlib_metadata.PackageNotFoundError:
        sdk_version = None

    versions = Table(title="Versions", show_header=False)
    versions.add_column("Component", style="cyan", no_wrap=True)
    versions.add_column("Version", style="bold")
    versions.add_row("a2a-lite", __version__)
    versions.add_row("a2a-sdk", sdk_version or "[red]not installed[/]")
    versions.add_row("Python", sys.version.split()[0])
    console.print(versions)

    # --- SDK compatibility --------------------------------------------------
    if sdk_version is None:
        healthy = False
        console.print(
            Panel(
                "[bold red]a2a-sdk is not installed.[/]\n\n"
                "Install it with:\n"
                '  pip install "a2a-sdk[http-server]>=1.1.2,<2.0"',
                title="Incompatible SDK",
                border_style="red",
            )
        )
    elif not _sdk_version_supported(sdk_version):
        healthy = False
        console.print(
            Panel(
                f"[bold yellow]a2a-sdk {sdk_version} is outside the supported range "
                f">={'.'.join(map(str, SDK_MIN_VERSION))},<{SDK_MAX_MAJOR}.0.[/]\n\n"
                "a2a-lite 1.0 targets A2A protocol v1.0. Please upgrade:\n"
                '  pip install "a2a-sdk[http-server]>=1.1.2,<2.0"',
                title="Incompatible SDK",
                border_style="yellow",
            )
        )
    else:
        console.print(
            f"[green]✅ a2a-sdk {sdk_version} is within the supported range "
            f"(>={'.'.join(map(str, SDK_MIN_VERSION))},<{SDK_MAX_MAJOR}.0)[/]"
        )

    # --- Features -----------------------------------------------------------
    features = Table(title="Features")
    features.add_column("Feature", style="cyan", no_wrap=True)
    features.add_column("Status", style="bold")
    features.add_row("JSON-RPC transport", "[green]✅[/]")
    features.add_row("REST transport", "[green]✅[/]")
    features.add_row(
        "gRPC transport",
        "[green]✅[/]" if find_spec("grpc") else "[dim]❌ (install a2a-sdk\\[grpc])[/]",
    )
    for label, module in (
        ("mcp extra", "mcp"),
        ("openai extra", "openai"),
        ("anthropic extra", "anthropic"),
        ("bedrock extra (boto3)", "boto3"),
        ("oauth extra (pyjwt)", "jwt"),
    ):
        features.add_row(label, "[green]✅[/]" if find_spec(module) else "[dim]❌[/]")
    console.print(features)

    # --- Optional remote agent ----------------------------------------------
    if url is not None:
        import httpx

        async def _check_remote():
            card = await _fetch_card(url)
            _check_card_version(card, url)

            console.print(
                Panel(
                    f"[bold]{card.get('name', 'Unknown')}[/] v{card.get('version', '?')}\n"
                    f"[dim]{card.get('description', '-')}[/]",
                    title=f"Remote Agent: {url}",
                    border_style="green",
                )
            )

            interfaces = card.get("supportedInterfaces", [])
            iface_table = Table(title="Interfaces / Transports")
            iface_table.add_column("URL", style="cyan", no_wrap=True)
            iface_table.add_column("Protocol Binding", style="green")
            iface_table.add_column("Protocol Version", style="yellow")
            for iface in interfaces:
                iface_table.add_row(
                    iface.get("url", "-"),
                    iface.get("protocolBinding", "-"),
                    iface.get("protocolVersion", "-"),
                )
            console.print(iface_table)

            versions_seen = {iface.get("protocolVersion", "?") for iface in interfaces}
            console.print(f"[bold]Protocol version(s):[/] {', '.join(sorted(versions_seen))}")

            signatures = card.get("signatures") or []
            if signatures:
                console.print(f"[green]✅ Card is signed ({len(signatures)} signature(s))[/]")

        try:
            asyncio.run(_check_remote())
        except typer.Exit:
            raise
        except httpx.HTTPError as e:
            console.print(f"[red]Error: Could not fetch agent card from {url}[/]")
            console.print(f"[dim]{e}[/]")
            raise typer.Exit(1)
        except Exception as e:
            console.print(f"[red]Error: {e}[/]")
            raise typer.Exit(1)

    if not healthy:
        raise typer.Exit(1)


def _find_a2a_lite_source() -> Path | None:
    """Locate a local a2a-lite source checkout (editable/dir install), if any.

    Returns the package root (containing pyproject.toml and src/a2a_lite),
    or None when the CLI was installed from a wheel (e.g. PyPI).
    """
    try:
        dist = importlib_metadata.distribution("a2a-lite")
        direct_url = dist.read_text("direct_url.json")
        if not direct_url:
            return None
        url = json.loads(direct_url).get("url", "")
        if url.startswith("file://"):
            src = Path(url[len("file://") :])
            if (src / "pyproject.toml").exists() and (src / "src" / "a2a_lite").is_dir():
                return src
    except Exception:
        pass
    return None


@app.command()
def create(
    name: str = typer.Argument(..., help="Project name"),
    path: Path | None = typer.Option(None, help="Directory to create project in"),
):
    """
    Create a full A2A Lite agent project (tests, Docker, README).

    Like `init`, but also generates a Dockerfile and docker-compose.yml.

    Example: a2a-lite create my-agent
    """
    project_path = path or Path(name)
    project_path.mkdir(exist_ok=True)

    safe_name = name.lower().replace(" ", "-").replace("_", "-")

    (project_path / "agent.py").write_text(
        f'''"""
{name} - A2A Lite Agent

Run with: python agent.py
"""
from a2a_lite import Agent

agent = Agent(
    name="{name}",
    description="A simple A2A Lite agent",
    version="1.0.0",
)


@agent.skill("hello", description="Say hello to someone")
async def hello(name: str = "World") -> str:
    """Greets the provided name."""
    return f"Hello, {{name}}!"


@agent.skill("echo", description="Echo back the input")
async def echo(message: str) -> dict:
    """Echoes the input message."""
    return {{"received": message, "echoed": True}}


if __name__ == "__main__":
    agent.run(port=8787)
'''
    )

    tests_dir = project_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_agent.py").write_text(
        f'''"""
Tests for {name} agent.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from a2a_lite import AgentTestClient

from agent import agent

client = AgentTestClient(agent)


def test_hello():
    result = client.call("hello", name="World")
    assert result == "Hello, World!"


def test_hello_custom_name():
    result = client.call("hello", name="A2A")
    assert result == "Hello, A2A!"


def test_echo():
    result = client.call("echo", message="test")
    assert result.data["received"] == "test"
    assert result.data["echoed"] is True
'''
    )

    (project_path / "pyproject.toml").write_text(
        f'''[project]
name = "{safe_name}"
version = "0.1.0"
description = "A2A Agent: {name}"
requires-python = ">=3.10"
dependencies = [
    "a2a-lite>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]
'''
    )

    (project_path / "README.md").write_text(
        f"""# {name}

An A2A Lite agent (A2A protocol v1.0).

## Quick Start

```bash
cd {project_path}
uv run agent.py
# or: a2a-lite serve agent.py
```

## Testing

```bash
# Using the CLI
a2a-lite test http://localhost:8787 hello -p name=World

# Using pytest
uv run pytest tests/
```

## Docker

```bash
docker compose up --build
# Agent available at http://localhost:8787
```

> **Note:** until `a2a-lite` 1.0.0 is published on PyPI, the project vendors the
> library from your local checkout (`vendor/a2a-lite/`) so `docker build` works
> today. For local development outside Docker, install it with
> `pip install "git+https://github.com/xvierd/a2a-lite#subdirectory=packages/python"`.
> Once the release is on PyPI, delete `vendor/` and replace the dependency with
> `"a2a-lite>=1.0.0"` (in `pyproject.toml` and the `Dockerfile`).
"""
    )

    (project_path / ".gitignore").write_text("__pycache__/\n*.pyc\n.venv/\ndist/\n*.egg-info/\n.pytest_cache/\n")

    # a2a-lite 1.0 is not on PyPI yet: when the CLI itself runs from a local
    # source checkout, vendor it into the project so `docker build` works today.
    import shutil

    source = _find_a2a_lite_source()
    if source is not None:
        vendor_dir = project_path / "vendor" / "a2a-lite"
        if vendor_dir.exists():
            shutil.rmtree(vendor_dir)
        vendor_dir.mkdir(parents=True)
        shutil.copy2(source / "pyproject.toml", vendor_dir / "pyproject.toml")
        if (source / "README.md").exists():
            shutil.copy2(source / "README.md", vendor_dir / "README.md")
        shutil.copytree(source / "src", vendor_dir / "src")

        dockerfile = """FROM python:3.12-slim

WORKDIR /app
COPY agent.py .

# a2a-lite 1.0 is vendored from your local checkout (not on PyPI yet).
# Once a2a-lite>=1.0.0 is published, delete vendor/ and replace the two
# lines below with:
#   RUN pip install --no-cache-dir "a2a-lite>=1.0.0"
COPY vendor/ ./vendor/
RUN pip install --no-cache-dir ./vendor/a2a-lite

EXPOSE 8787
CMD ["a2a-lite", "serve", "agent.py", "--port", "8787"]
"""
    else:
        dockerfile = """FROM python:3.12-slim

WORKDIR /app
COPY agent.py .

RUN pip install --no-cache-dir "a2a-lite>=1.0.0"

EXPOSE 8787
CMD ["a2a-lite", "serve", "agent.py", "--port", "8787"]
"""

    (project_path / "Dockerfile").write_text(dockerfile)

    (project_path / "docker-compose.yml").write_text(
        """services:
  agent:
    build: .
    ports:
      - "8787:8787"
"""
    )

    tree = Tree(f"[bold green]{project_path}/[/]")
    tree.add("agent.py")
    tests_branch = tree.add("tests/")
    tests_branch.add("test_agent.py")
    tree.add("pyproject.toml")
    tree.add("README.md")
    tree.add("Dockerfile")
    tree.add("docker-compose.yml")
    tree.add(".gitignore")
    if source is not None:
        tree.add("vendor/a2a-lite/  (local a2a-lite source, until 1.0 is on PyPI)")

    console.print(
        Panel(
            f"[green]Created project: {name}[/]\n\n"
            f"[bold]Next steps:[/]\n"
            f"  cd {project_path}\n"
            f"  uv run pytest tests/          # run the tests\n"
            f"  uv run agent.py               # start the agent\n"
            f"  a2a-lite doctor http://localhost:8787\n"
            f"  docker compose up --build     # run in Docker",
            title="A2A Lite Project Created",
            border_style="green",
        )
    )
    console.print(tree)


@app.command()
def serve(
    file: Path = typer.Argument(..., help="Python file containing the agent"),
    port: int = typer.Option(8787, help="Port to run on"),
):
    """
    Run an agent from a Python file.

    The file should define an 'agent' variable of type Agent.
    """
    import importlib.util
    import sys

    # Load the module
    file = file.resolve()
    spec = importlib.util.spec_from_file_location("agent_module", file)
    if spec is None or spec.loader is None:
        console.print(f"[red]Error: Could not load {file}[/]")
        raise typer.Exit(1)

    module = importlib.util.module_from_spec(spec)
    sys.modules["agent_module"] = module

    # Change to the file's directory for relative imports
    original_cwd = Path.cwd()
    try:
        import os

        os.chdir(file.parent)
        spec.loader.exec_module(module)
    finally:
        os.chdir(original_cwd)

    # Find the agent
    if not hasattr(module, "agent"):
        console.print("[red]Error: No 'agent' variable found in file[/]")
        console.print("[dim]Make sure your file defines: agent = Agent(...)[/]")
        raise typer.Exit(1)

    agent = module.agent
    agent.run(port=port)


@app.command()
def version():
    """Show A2A Lite version."""
    from . import __version__

    console.print(f"A2A Lite v{__version__}")


@app.callback()
def main():
    """
    A2A Lite - Simplified A2A Protocol SDK

    Build A2A agents with minimal boilerplate.
    """
    pass


if __name__ == "__main__":
    app()
