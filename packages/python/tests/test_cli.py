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
        assert "a2a-lite>=0.2.5" in content


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
        result = runner.invoke(app, [
            "discover",
            "http://invalid-nonexistent-url-12345.example.com",
        ])
        # Should not crash, shows error in table
        assert result.exit_code == 0
        assert "Error" in result.stdout or "error" in result.stdout.lower()
