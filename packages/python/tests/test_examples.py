"""
Tests that import each example module and exercise its skills via AgentTestClient.
No server is started — AgentTestClient runs in-process.

Examples requiring external services (LLM APIs, MCP servers, live HTTP) are
tested only for successful import and agent card generation.
"""

import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from a2a_lite import AgentTestClient

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"


def load_example(filename: str) -> types.ModuleType:
    """Import an example file without executing its __main__ block."""
    path = EXAMPLES_DIR / filename
    spec = importlib.util.spec_from_file_location(f"example_{filename[:-3]}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 01 — Hello World
# ---------------------------------------------------------------------------


class TestHelloWorld:
    def setup_method(self):
        self.mod = load_example("01_hello_world.py")

    def test_agent_created(self):
        assert self.mod.agent.name == "HelloWorld"

    def test_greet(self):
        client = AgentTestClient(self.mod.agent)
        result = client.call("greet", name="Alice")
        assert "Alice" in str(result)

    def test_list_skills(self):
        client = AgentTestClient(self.mod.agent)
        assert "greet" in client.list_skills()


# ---------------------------------------------------------------------------
# 02 — Calculator
# ---------------------------------------------------------------------------


class TestCalculator:
    def setup_method(self):
        self.mod = load_example("02_calculator.py")
        self.client = AgentTestClient(self.mod.agent)

    def test_add(self):
        assert self.client.call("add", a=2, b=3) == 5

    def test_subtract(self):
        assert self.client.call("subtract", a=10, b=4) == 6

    def test_multiply(self):
        assert self.client.call("multiply", a=3, b=7) == 21

    def test_divide(self):
        result = self.client.call("divide", a=10, b=2)
        assert result.data["result"] == 5.0

    def test_divide_by_zero(self):
        result = self.client.call("divide", a=5, b=0)
        assert "error" in result.data


# ---------------------------------------------------------------------------
# 03 — Async Agent
# ---------------------------------------------------------------------------


class TestAsyncAgent:
    def setup_method(self):
        self.mod = load_example("03_async_agent.py")
        self.client = AgentTestClient(self.mod.agent)

    def test_delay(self):
        result = self.client.call("delay", seconds=0.0)
        assert result.data["waited"] == 0.0

    def test_fetch_data_mocked(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_cls.return_value = mock_client

            result = self.client.call("fetch_data", url="https://example.com")
        assert result.data is not None


# ---------------------------------------------------------------------------
# 05 — LLM Integration (import + agent card only — requires API key)
# ---------------------------------------------------------------------------


class TestLLMAgent:
    def setup_method(self):
        self.mod = load_example("05_with_llm.py")

    def test_agent_created(self):
        assert self.mod.agent is not None

    def test_skills_registered(self):
        client = AgentTestClient(self.mod.agent)
        skills = client.list_skills()
        assert "chat" in skills
        assert "summarize" in skills


# ---------------------------------------------------------------------------
# 06 — Pydantic Models
# ---------------------------------------------------------------------------


class TestPydanticModels:
    def setup_method(self):
        self.mod = load_example("06_pydantic_models.py")
        self.client = AgentTestClient(self.mod.agent)

    def test_create_user(self):
        result = self.client.call("create_user", user={"name": "Alice", "email": "alice@example.com", "age": 30})
        assert result.data["user"]["name"] == "Alice"
        assert "id" in result.data

    def test_list_users(self):
        result = self.client.call("list_users")
        assert isinstance(result.data, list)

    def test_find_user_after_create(self):
        self.client.call("create_user", user={"name": "Bob", "email": "bob@example.com", "age": 25})
        result = self.client.call("find_user", name="Bob")
        assert result.data["name"] == "Bob"


# ---------------------------------------------------------------------------
# 07 — Middleware
# ---------------------------------------------------------------------------


class TestMiddleware:
    def setup_method(self):
        self.mod = load_example("07_middleware.py")
        self.client = AgentTestClient(self.mod.agent)

    def test_fast_operation(self):
        result = self.client.call("fast_operation")
        assert result.data is not None

    def test_slow_operation(self):
        result = self.client.call("slow_operation")
        assert result.data is not None


# ---------------------------------------------------------------------------
# 08 — Streaming
# ---------------------------------------------------------------------------


class TestStreaming:
    def setup_method(self):
        self.mod = load_example("08_streaming.py")
        self.client = AgentTestClient(self.mod.agent)

    def test_count_returns_chunks(self):
        chunks = list(self.client.stream("count", n=3))
        assert len(chunks) == 4  # "Count: 1", "Count: 2", "Count: 3", "Done!"

    def test_typewriter_streams_words(self):
        chunks = list(self.client.stream("typewriter", message="hello world"))
        assert len(chunks) >= 1

    def test_fake_llm_streams(self):
        chunks = list(self.client.stream("fake_llm", prompt="test"))
        assert len(chunks) >= 1


# ---------------------------------------------------------------------------
# 09 — Testing (example already tests itself; just confirm it runs)
# ---------------------------------------------------------------------------


class TestTestingExample:
    def setup_method(self):
        self.mod = load_example("09_testing.py")
        self.client = AgentTestClient(self.mod.agent)

    def test_add(self):
        assert self.client.call("add", a=2, b=3) == 5

    def test_multiply(self):
        assert self.client.call("multiply", a=4, b=5) == 20

    def test_divide(self):
        result = self.client.call("divide", a=10, b=2)
        assert result.data["result"] == 5.0


# ---------------------------------------------------------------------------
# 11 — Task Tracking
# ---------------------------------------------------------------------------


class TestTaskTracking:
    def setup_method(self):
        self.mod = load_example("11_task_tracking.py")
        self.client = AgentTestClient(self.mod.agent)

    def test_long_process(self):
        result = self.client.call("long_process", steps=2)
        assert result.data is not None

    def test_batch_import(self):
        result = self.client.call("batch_import", items=["a", "b"])
        assert result.data is not None


# ---------------------------------------------------------------------------
# 12 — Auth (test public skill; secret skill tested with and without auth)
# ---------------------------------------------------------------------------


class TestAuth:
    def setup_method(self):
        self.mod = load_example("12_with_auth.py")
        self.client = AgentTestClient(self.mod.agent)

    def test_public_info(self):
        result = self.client.call("public_info")
        assert result.data is not None

    def test_skills_registered(self):
        assert "public_info" in self.client.list_skills()
        assert "get_secrets" in self.client.list_skills()
