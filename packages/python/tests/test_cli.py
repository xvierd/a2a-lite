"""
Tests for the CLI module.
"""

import pytest
from typer.testing import CliRunner

from a2a_lite.cli import app

runner = CliRunner()


class TestVersion:
    def test_version_command(self):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        # Output is "A2A Lite v0.2.5"
        assert "a2a lite" in result.stdout.lower()


class TestInit:
    def test_init_creates_project(self, tmp_path):
        # The CLI uses --path as the direct directory (not path/name)
        project_dir = tmp_path / "my-agent"
        result = runner.invoke(app, ["init", "my-agent", "--path", str(project_dir)])
        assert result.exit_code == 0

        # Check that agent file was created
        agent_file = project_dir / "agent.py"
        assert agent_file.exists()

        # Check content
        content = agent_file.read_text()
        assert "Agent" in content
        assert "skill" in content
        assert "my-agent" in content

    def test_init_creates_pyproject(self, tmp_path):
        project_dir = tmp_path / "test-project"
        result = runner.invoke(app, ["init", "test-project", "--path", str(project_dir)])
        assert result.exit_code == 0

        pyproject = project_dir / "pyproject.toml"
        assert pyproject.exists()

        content = pyproject.read_text()
        assert "test-project" in content

    def test_init_creates_readme(self, tmp_path):
        project_dir = tmp_path / "readme-test"
        result = runner.invoke(app, ["init", "readme-test", "--path", str(project_dir)])
        assert result.exit_code == 0

        readme = project_dir / "README.md"
        assert readme.exists()

    def test_init_without_path(self, tmp_path, monkeypatch):
        """Init without --path creates a directory with the project name."""
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init", "new-agent"])
        assert result.exit_code == 0

        agent_file = tmp_path / "new-agent" / "agent.py"
        assert agent_file.exists()

    def test_init_creates_test_file(self, tmp_path):
        """Init should create tests/test_agent.py."""
        project_dir = tmp_path / "test-scaffold"
        result = runner.invoke(app, ["init", "test-scaffold", "--path", str(project_dir)])
        assert result.exit_code == 0

        test_file = project_dir / "tests" / "test_agent.py"
        assert test_file.exists()

        content = test_file.read_text()
        assert "AgentTestClient" in content
        assert "test_hello" in content

    def test_init_creates_gitignore(self, tmp_path):
        """Init should create .gitignore."""
        project_dir = tmp_path / "gitignore-test"
        result = runner.invoke(app, ["init", "gitignore-test", "--path", str(project_dir)])
        assert result.exit_code == 0

        gitignore = project_dir / ".gitignore"
        assert gitignore.exists()

        content = gitignore.read_text()
        assert "__pycache__" in content
        assert ".venv" in content

    def test_init_pyproject_has_dev_deps(self, tmp_path):
        """Init pyproject should include dev dependencies."""
        project_dir = tmp_path / "dev-deps-test"
        result = runner.invoke(app, ["init", "dev-deps-test", "--path", str(project_dir)])
        assert result.exit_code == 0

        content = (project_dir / "pyproject.toml").read_text()
        assert "pytest" in content
        assert "a2a-lite>=1.0.0" in content


class TestInspect:
    def test_inspect_invalid_url(self):
        """Inspect should handle invalid URLs gracefully."""
        result = runner.invoke(app, ["inspect", "http://invalid-nonexistent-url-12345.example.com"])
        # Should fail but not crash
        assert result.exit_code != 0 or "error" in result.stdout.lower()


class TestTest:
    def test_test_invalid_url(self):
        """Test command should handle invalid URLs gracefully."""
        result = runner.invoke(app, ["test", "http://invalid-nonexistent-url-12345.example.com", "hello"])
        # Should fail but not crash
        assert result.exit_code != 0 or "error" in result.stdout.lower()

    def test_test_json_flag_exists(self):
        """Test command should accept --json flag."""
        result = runner.invoke(app, ["test", "--help"])
        assert "--json" in result.stdout or "-j" in result.stdout


class TestDiscover:
    def test_discover_invalid_urls(self):
        """Discover should handle invalid URLs gracefully."""
        result = runner.invoke(
            app,
            [
                "discover",
                "http://invalid-nonexistent-url-12345.example.com",
            ],
        )
        # Should not crash, shows error in table
        assert result.exit_code == 0
        assert "Error" in result.stdout or "error" in result.stdout.lower()


V1_CARD = {
    "name": "RemoteBot",
    "description": "A v1.0 agent",
    "version": "1.0.0",
    "supportedInterfaces": [
        {"url": "http://localhost:8787/", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"},
        {"url": "http://localhost:8787/", "protocolBinding": "HTTP+JSON", "protocolVersion": "1.0"},
    ],
    "capabilities": {"streaming": True, "pushNotifications": False},
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain"],
    "skills": [{"id": "hello", "name": "hello", "description": "Say hi", "tags": ["greeting"]}],
    "signatures": [{"protected": "abc", "signature": "xyz", "header": {}}],
}

V03_CARD = {
    "name": "LegacyBot",
    "description": "A 0.3 agent",
    "url": "http://localhost:8787/",
    "protocolVersion": "0.3.0",
    "version": "1.0.0",
    "capabilities": {},
    "skills": [],
}


def _mock_card(monkeypatch, card):
    async def fake_fetch(url, timeout=10.0):
        return card

    monkeypatch.setattr("a2a_lite.cli._fetch_card", fake_fetch)


class TestDoctor:
    def test_doctor_local_ok(self):
        """Doctor without URL reports versions and features, exit 0."""
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "a2a-sdk" in result.stdout
        assert "JSON-RPC" in result.stdout
        assert "REST" in result.stdout
        assert "gRPC" in result.stdout

    def test_doctor_unsupported_sdk_exits_1(self, monkeypatch):
        """Doctor exits 1 when a2a-sdk is outside the supported range."""
        monkeypatch.setattr("a2a_lite.cli.importlib_metadata.version", lambda name: "0.30.0")
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "outside the supported range" in result.stdout

    def test_doctor_sdk_not_installed_exits_1(self, monkeypatch):
        """Doctor exits 1 when a2a-sdk is missing."""
        import importlib.metadata

        def raise_not_found(name):
            raise importlib.metadata.PackageNotFoundError(name)

        monkeypatch.setattr("a2a_lite.cli.importlib_metadata.version", raise_not_found)
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 1
        assert "not installed" in result.stdout

    def test_doctor_with_v1_url(self, monkeypatch):
        """Doctor with a URL verifies a v1.0 remote agent."""
        _mock_card(monkeypatch, V1_CARD)
        result = runner.invoke(app, ["doctor", "http://localhost:8787"])
        assert result.exit_code == 0
        assert "RemoteBot" in result.stdout
        assert "JSONRPC" in result.stdout
        assert "1.0" in result.stdout
        assert "signed" in result.stdout

    def test_doctor_with_v03_url(self, monkeypatch):
        """Doctor rejects a 0.3 remote agent with a clear panel."""
        _mock_card(monkeypatch, V03_CARD)
        result = runner.invoke(app, ["doctor", "http://localhost:8787"])
        assert result.exit_code == 1
        assert "speaks A2A 0.3" in result.stdout
        assert "requires protocol v1.0" in result.stdout


class TestCreate:
    def test_create_generates_all_files(self, tmp_path):
        project_dir = tmp_path / "full-agent"
        result = runner.invoke(app, ["create", "full-agent", "--path", str(project_dir)])
        assert result.exit_code == 0

        for rel in (
            "agent.py",
            "tests/test_agent.py",
            "pyproject.toml",
            "README.md",
            ".gitignore",
            "Dockerfile",
            "docker-compose.yml",
        ):
            assert (project_dir / rel).exists(), f"missing {rel}"

    def test_create_agent_py_compiles(self, tmp_path):
        project_dir = tmp_path / "compile-agent"
        result = runner.invoke(app, ["create", "compile-agent", "--path", str(project_dir)])
        assert result.exit_code == 0
        compile((project_dir / "agent.py").read_text(), "agent.py", "exec")

    def test_create_dockerfile(self, tmp_path):
        project_dir = tmp_path / "docker-agent"
        result = runner.invoke(app, ["create", "docker-agent", "--path", str(project_dir)])
        assert result.exit_code == 0

        dockerfile = (project_dir / "Dockerfile").read_text()
        assert "python:3.12-slim" in dockerfile
        assert "EXPOSE 8787" in dockerfile
        if (project_dir / "vendor" / "a2a-lite").is_dir():
            # a2a-lite installed from a local checkout -> vendored into the project
            assert "RUN pip install --no-cache-dir ./vendor/a2a-lite" in dockerfile
        else:
            assert 'RUN pip install --no-cache-dir "a2a-lite>=1.0.0"' in dockerfile

        compose = (project_dir / "docker-compose.yml").read_text()
        assert "8787:8787" in compose

    def test_create_vendors_local_source(self, tmp_path, monkeypatch):
        """When a2a-lite runs from a local checkout, create vendors it for Docker."""
        fake_src = tmp_path / "fake-a2a-lite"
        (fake_src / "src" / "a2a_lite").mkdir(parents=True)
        (fake_src / "pyproject.toml").write_text('[project]\nname = "a2a-lite"\nversion = "1.0.0"\n')
        monkeypatch.setattr("a2a_lite.cli._find_a2a_lite_source", lambda: fake_src)

        project_dir = tmp_path / "vendored-agent"
        result = runner.invoke(app, ["create", "vendored-agent", "--path", str(project_dir)])
        assert result.exit_code == 0

        assert (project_dir / "vendor" / "a2a-lite" / "pyproject.toml").exists()
        assert (project_dir / "vendor" / "a2a-lite" / "src" / "a2a_lite").is_dir()
        dockerfile = (project_dir / "Dockerfile").read_text()
        assert "COPY vendor/ ./vendor/" in dockerfile
        assert "RUN pip install --no-cache-dir ./vendor/a2a-lite" in dockerfile

    def test_create_pyproject_dep(self, tmp_path):
        project_dir = tmp_path / "dep-agent"
        result = runner.invoke(app, ["create", "dep-agent", "--path", str(project_dir)])
        assert result.exit_code == 0
        assert "a2a-lite>=1.0.0" in (project_dir / "pyproject.toml").read_text()

    def test_create_test_uses_test_client(self, tmp_path):
        project_dir = tmp_path / "test-agent"
        result = runner.invoke(app, ["create", "test-agent", "--path", str(project_dir)])
        assert result.exit_code == 0
        content = (project_dir / "tests" / "test_agent.py").read_text()
        assert "AgentTestClient" in content
        compile(content, "test_agent.py", "exec")

    def test_create_docker_build_smoke(self, tmp_path):
        """Real `docker build` of a generated project (skipped if Docker is unavailable)."""
        import shutil
        import subprocess

        if shutil.which("docker") is None:
            pytest.skip("docker CLI not installed")
        try:
            probe = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pytest.skip("docker daemon not reachable")
        if probe.returncode != 0:
            pytest.skip("docker daemon not reachable")

        project_dir = tmp_path / "docker-smoke-agent"
        result = runner.invoke(app, ["create", "docker-smoke-agent", "--path", str(project_dir)])
        assert result.exit_code == 0
        assert (project_dir / "Dockerfile").exists()

        # Prefer vendored path (local checkout); PyPI path only works after 1.0 is published.
        build = subprocess.run(
            ["docker", "build", "-t", "a2a-lite-cli-create-smoke", str(project_dir)],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
        assert build.returncode == 0, (
            f"docker build failed (exit {build.returncode}):\n"
            f"stdout:\n{build.stdout[-2000:]}\n"
            f"stderr:\n{build.stderr[-2000:]}"
        )


class TestV03Detection:
    def test_inspect_v03_panel(self, monkeypatch):
        """Inspect shows a clear panel for 0.3 agents."""
        _mock_card(monkeypatch, V03_CARD)
        result = runner.invoke(app, ["inspect", "http://localhost:8787"])
        assert result.exit_code == 1
        assert "speaks A2A 0.3" in result.stdout
        assert "requires protocol v1.0" in result.stdout

    def test_info_v03_panel(self, monkeypatch):
        _mock_card(monkeypatch, V03_CARD)
        result = runner.invoke(app, ["info", "http://localhost:8787"])
        assert result.exit_code == 1
        assert "speaks A2A 0.3" in result.stdout

    def test_test_v03_panel(self, monkeypatch):
        _mock_card(monkeypatch, V03_CARD)
        result = runner.invoke(app, ["test", "http://localhost:8787", "hello"])
        assert result.exit_code == 1
        assert "speaks A2A 0.3" in result.stdout

    def test_discover_v03_marks_row(self, monkeypatch):
        """Discover marks 0.3 agents without crashing."""
        _mock_card(monkeypatch, V03_CARD)
        result = runner.invoke(app, ["discover", "http://localhost:8787"])
        assert result.exit_code == 0
        assert "speaks A2A 0.3" in result.stdout

    def test_inspect_v1_shows_interfaces(self, monkeypatch):
        """Inspect shows interfaces/transports, capabilities, and signatures."""
        _mock_card(monkeypatch, V1_CARD)
        result = runner.invoke(app, ["inspect", "http://localhost:8787"])
        assert result.exit_code == 0
        assert "JSONRPC" in result.stdout
        assert "HTTP+JSON" in result.stdout
        assert "Signatures" in result.stdout
        assert "greeting" in result.stdout
