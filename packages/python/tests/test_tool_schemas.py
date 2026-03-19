"""
Tests for Agent.get_tool_schemas() method.
"""

import pytest

from a2a_lite import Agent


class TestGetToolSchemas:
    """Tests for the get_tool_schemas method."""

    def test_basic_skill_schema(self):
        """Test schema generation for a simple skill."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("greet", description="Greet someone")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        schemas = agent.get_tool_schemas()

        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "greet"
        assert schema["function"]["description"] == "Greet someone"
        assert "name" in schema["function"]["parameters"]["properties"]

    def test_multiple_skills_schema(self):
        """Test schema generation with multiple skills."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("add")
        async def add(a: int, b: int) -> int:
            return a + b

        @agent.skill("greet")
        async def greet(name: str) -> str:
            return f"Hello, {name}!"

        schemas = agent.get_tool_schemas()
        assert len(schemas) == 2

        names = {s["function"]["name"] for s in schemas}
        assert names == {"add", "greet"}

    def test_schema_filters_task_context(self):
        """Test that TaskContext parameter is filtered from schema."""
        from a2a_lite.tasks import TaskContext

        agent = Agent(name="Test", description="Test", task_store="memory")

        @agent.skill("process")
        async def process(data: str, task: TaskContext) -> str:
            return data

        schemas = agent.get_tool_schemas()
        props = schemas[0]["function"]["parameters"]["properties"]

        assert "data" in props
        assert "task" not in props

    def test_schema_filters_auth_result(self):
        """Test that AuthResult parameter is filtered from schema."""
        from a2a_lite.auth import AuthResult

        agent = Agent(name="Test", description="Test")

        @agent.skill("whoami")
        async def whoami(query: str, auth: AuthResult) -> str:
            return "ok"

        schemas = agent.get_tool_schemas()
        props = schemas[0]["function"]["parameters"]["properties"]

        assert "query" in props
        assert "auth" not in props

    def test_schema_filters_mcp_client(self):
        """Test that MCPClient parameter is filtered from schema."""
        from a2a_lite.mcp import MCPClient

        agent = Agent(name="Test", description="Test")

        @agent.skill("research")
        async def research(query: str, mcp: MCPClient) -> str:
            return "result"

        schemas = agent.get_tool_schemas()
        props = schemas[0]["function"]["parameters"]["properties"]

        assert "query" in props
        assert "mcp" not in props

    def test_schema_filters_required_list(self):
        """Test that injected params are removed from required list too."""
        from a2a_lite.tasks import TaskContext

        agent = Agent(name="Test", description="Test", task_store="memory")

        @agent.skill("process")
        async def process(data: str, task: TaskContext) -> str:
            return data

        schemas = agent.get_tool_schemas()
        required = schemas[0]["function"]["parameters"].get("required", [])

        assert "data" in required
        assert "task" not in required

    def test_unsupported_format_raises(self):
        """Test that unsupported format raises ValueError."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("test")
        async def test_skill() -> str:
            return "ok"

        with pytest.raises(ValueError, match="Unsupported schema format"):
            agent.get_tool_schemas(format="anthropic")

    def test_skill_with_no_params(self):
        """Test schema for a skill with no parameters."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("ping")
        async def ping() -> str:
            return "pong"

        schemas = agent.get_tool_schemas()
        assert len(schemas) == 1
        params = schemas[0]["function"]["parameters"]
        # Should have a valid schema even with no params
        assert "type" in params or "properties" in params

    def test_empty_skills(self):
        """Test schema generation with no skills registered."""
        agent = Agent(name="Test", description="Test")
        schemas = agent.get_tool_schemas()
        assert schemas == []

    def test_schema_with_default_params(self):
        """Test schema generation for skill with default parameters."""
        agent = Agent(name="Test", description="Test")

        @agent.skill("greet")
        async def greet(name: str = "World") -> str:
            return f"Hello, {name}!"

        schemas = agent.get_tool_schemas()
        params = schemas[0]["function"]["parameters"]

        assert "name" in params["properties"]
        # name should NOT be in required since it has a default
        assert "name" not in params.get("required", [])


class TestGetToolSchemasMultipleInjected:
    """Test filtering when multiple injected params are present."""

    def test_all_injected_params_filtered(self):
        """Test that all three injected param types are filtered simultaneously."""
        from a2a_lite.auth import AuthResult
        from a2a_lite.mcp import MCPClient
        from a2a_lite.tasks import TaskContext

        agent = Agent(name="Test", description="Test", task_store="memory")

        @agent.skill("complex")
        async def complex_skill(
            data: str,
            task: TaskContext,
            auth: AuthResult,
            mcp: MCPClient,
        ) -> str:
            return data

        schemas = agent.get_tool_schemas()
        props = schemas[0]["function"]["parameters"]["properties"]

        assert "data" in props
        assert "task" not in props
        assert "auth" not in props
        assert "mcp" not in props
