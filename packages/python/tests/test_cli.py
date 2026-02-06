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
        # Output is "A2A Lite v0.2.3"
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
