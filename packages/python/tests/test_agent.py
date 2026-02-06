"""
Tests for the Agent class.
"""
import pytest
from a2a_lite import Agent


def test_agent_creation():
    """Test basic agent creation."""
    agent = Agent(name="Test", description="Test agent")
    assert agent.name == "Test"
    assert agent.description == "Test agent"
    assert agent.version == "1.0.0"


def test_agent_with_custom_version():
    """Test agent with custom version."""
    agent = Agent(name="Test", description="Test", version="2.5.0")
    assert agent.version == "2.5.0"


def test_skill_registration():
    """Test that skills are properly registered."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("greet")
    async def greet(name: str) -> str:
        return f"Hello, {name}"

    assert "greet" in agent._skills
    assert agent._skills["greet"].name == "greet"
    assert agent._skills["greet"].is_async is True


def test_skill_with_custom_name():
    """Test skill registration with custom name."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("custom_name", description="Custom description")
    async def my_func(x: int) -> int:
        return x * 2

    assert "custom_name" in agent._skills
    assert "my_func" not in agent._skills
    assert agent._skills["custom_name"].description == "Custom description"


def test_skill_input_schema_extraction():
    """Test that input schemas are extracted from type hints."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("add")
    async def add(a: int, b: int) -> int:
        return a + b

    skill = agent._skills["add"]
    assert skill.input_schema["properties"]["a"]["type"] == "integer"
    assert skill.input_schema["properties"]["b"]["type"] == "integer"
    assert "a" in skill.input_schema["required"]
    assert "b" in skill.input_schema["required"]


def test_skill_with_default_params():
    """Test schema extraction with default parameters."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("greet")
    async def greet(name: str = "World") -> str:
        return f"Hello, {name}"

    skill = agent._skills["greet"]
    assert "name" in skill.input_schema["properties"]
    assert "name" not in skill.input_schema["required"]  # Has default


def test_skill_output_schema():
    """Test output schema extraction."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("get_data")
    async def get_data() -> dict:
        return {"key": "value"}

    skill = agent._skills["get_data"]
    assert skill.output_schema["type"] == "object"


def test_multiple_skills():
    """Test registering multiple skills."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("skill1")
    async def skill1() -> str:
        return "one"

    @agent.skill("skill2")
    async def skill2() -> str:
        return "two"

    @agent.skill("skill3")
    async def skill3() -> str:
        return "three"

    assert len(agent._skills) == 3
    assert "skill1" in agent._skills
    assert "skill2" in agent._skills
    assert "skill3" in agent._skills


def test_agent_card_generation():
    """Test Agent Card generation."""
    agent = Agent(name="Test", description="A test agent", version="2.0.0")

    @agent.skill("greet", description="Greet someone")
    async def greet(name: str) -> str:
        return f"Hello, {name}"

    card = agent.build_agent_card("localhost", 8787)

    assert card.name == "Test"
    assert card.description == "A test agent"
    assert card.version == "2.0.0"
    assert len(card.skills) == 1
    assert card.skills[0].name == "greet"
    assert card.skills[0].description == "Greet someone"


def test_agent_card_url():
    """Test Agent Card URL generation."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("test")
    async def test_skill() -> str:
        return "test"

    card = agent.build_agent_card("example.com", 9000)
    assert card.url == "http://example.com:9000"


def test_agent_card_custom_url():
    """Test Agent Card with custom URL."""
    agent = Agent(name="Test", description="Test", url="https://my-agent.example.com")

    @agent.skill("test")
    async def test_skill() -> str:
        return "test"

    card = agent.build_agent_card()
    assert card.url == "https://my-agent.example.com"


def test_error_handler_registration():
    """Test error handler registration."""
    agent = Agent(name="Test", description="Test")

    @agent.on_error
    async def handle_error(error):
        return {"error": str(error)}

    assert agent._error_handler is not None


def test_startup_hook_registration():
    """Test startup hook registration."""
    agent = Agent(name="Test", description="Test")

    @agent.on_startup
    async def startup():
        pass

    assert len(agent._on_startup) == 1


def test_shutdown_hook_registration():
    """Test shutdown hook registration."""
    agent = Agent(name="Test", description="Test")

    @agent.on_shutdown
    async def shutdown():
        pass

    assert len(agent._on_shutdown) == 1


def test_sync_skill():
    """Test that sync skills are also supported."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("sync_skill")
    def sync_skill(x: int) -> int:
        return x * 2

    skill = agent._skills["sync_skill"]
    assert skill.is_async is False


def test_skill_with_tags():
    """Test skill with tags."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("tagged", tags=["math", "calculation"])
    async def tagged(a: int, b: int) -> int:
        return a + b

    skill = agent._skills["tagged"]
    assert skill.tags == ["math", "calculation"]
