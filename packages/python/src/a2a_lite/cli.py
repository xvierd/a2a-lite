"""
Command-line interface for A2A Lite.
"""
import asyncio
import json
from pathlib import Path
from typing import Optional, List

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="a2a-lite",
    help="A2A Lite - Simplified Agent-to-Agent Protocol SDK",
    add_completion=False,
)
console = Console()


@app.command()
def init(
    name: str = typer.Argument(..., help="Project name"),
    path: Optional[Path] = typer.Option(None, help="Directory to create project in"),
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

    (project_path / "agent.py").write_text(
        agent_template.format(name=name)
    )

    # Create pyproject.toml
    safe_name = name.lower().replace(" ", "-").replace("_", "-")
    pyproject = f'''[project]
name = "{safe_name}"
version = "0.1.0"
description = "A2A Agent: {name}"
requires-python = ">=3.10"
dependencies = [
    "a2a-lite>=0.2.3",
]
'''
    (project_path / "pyproject.toml").write_text(pyproject)

    # Create README
    readme = f'''# {name}

An A2A Lite agent.

## Running

```bash
cd {project_path}
uv run agent.py
```

## Testing

```bash
a2a-lite test http://localhost:8787 hello -p name=World
```
'''
    (project_path / "README.md").write_text(readme)

    console.print(Panel(
        f"[green]✅ Created project: {name}[/]\n\n"
        f"[dim]Files created:[/]\n"
        f"  • {project_path}/agent.py\n"
        f"  • {project_path}/pyproject.toml\n"
        f"  • {project_path}/README.md\n\n"
        f"[bold]Next steps:[/]\n"
        f"  cd {project_path}\n"
        f"  uv run agent.py",
        title="🚀 A2A Lite Project Created",
        border_style="green",
    ))


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
        async with httpx.AsyncClient() as client:
            # Fetch agent card
            card_url = f"{url.rstrip('/')}/.well-known/agent.json"
            response = await client.get(card_url, timeout=10.0)
            response.raise_for_status()
            card = response.json()

            # Display
            table = Table(title=f"📋 {card.get('name', 'Unknown')} v{card.get('version', '?')}")
            table.add_column("Skill", style="cyan")
            table.add_column("Description", style="dim")
            table.add_column("Tags", style="green")

            for skill in card.get('skills', []):
                table.add_row(
                    skill.get('name', skill.get('id', '?')),
                    skill.get('description', '-'),
                    ", ".join(skill.get('tags', [])) or "-",
                )

            console.print(f"\n[dim]URL: {card.get('url', url)}[/]")
            console.print(f"[dim]Description: {card.get('description', '-')}[/]\n")
            console.print(table)

    try:
        asyncio.run(_inspect())
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
    params: Optional[List[str]] = typer.Option(
        None, "--param", "-p",
        help="Parameters as key=value pairs"
    ),
):
    """
    Test an agent skill.

    Example: a2a-lite test http://localhost:8787 hello -p name=World
    """
    import httpx
    from uuid import uuid4

    # Parse parameters
    param_dict = {}
    for p in (params or []):
        if "=" in p:
            key, value = p.split("=", 1)
            # Try to parse as JSON for complex types
            try:
                param_dict[key] = json.loads(value)
            except json.JSONDecodeError:
                param_dict[key] = value

    async def _test():
        async with httpx.AsyncClient() as client:
            # Build request
            message = json.dumps({
                "skill": skill,
                "params": param_dict,
            })

            request_body = {
                "jsonrpc": "2.0",
                "method": "message/send",
                "id": uuid4().hex,
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"type": "text", "text": message}],
                        "messageId": uuid4().hex,
                    }
                }
            }

            response = await client.post(
                url,
                json=request_body,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()

            # Extract and display result
            console.print("\n[bold green]Response:[/]")
            console.print_json(json.dumps(result, indent=2))

    try:
        asyncio.run(_test())
    except httpx.HTTPError as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise typer.Exit(1)


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
    if not hasattr(module, 'agent'):
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
