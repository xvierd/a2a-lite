"""
Tests for the testing utilities.
"""
import pytest
from a2a_lite import Agent, AgentTestClient


@pytest.fixture
def simple_agent():
    """Create a simple agent for testing."""
    agent = Agent(name="TestAgent", description="For testing")

    @agent.skill("add")
    async def add(a: int, b: int) -> int:
        return a + b

    @agent.skill("greet")
    async def greet(name: str = "World") -> str:
        return f"Hello, {name}!"

    @agent.skill("get_dict")
    async def get_dict(key: str) -> dict:
        return {"key": key, "value": 42}

    return agent


def test_test_client_call(simple_agent):
    """Test calling a skill through TestClient."""
    client = AgentTestClient(simple_agent)
    result = client.call("add", a=2, b=3)
    assert result == 5


def test_test_client_with_defaults(simple_agent):
    """Test calling skill with default parameters."""
    client = AgentTestClient(simple_agent)
    result = client.call("greet")
    assert result == "Hello, World!"


def test_test_client_with_params(simple_agent):
    """Test calling skill with custom parameters."""
    client = AgentTestClient(simple_agent)
    result = client.call("greet", name="Alice")
    assert result == "Hello, Alice!"


def test_test_client_dict_result(simple_agent):
    """Test skill returning dict."""
    client = AgentTestClient(simple_agent)
    result = client.call("get_dict", key="test")
    assert result == {"key": "test", "value": 42}


def test_test_client_list_skills(simple_agent):
    """Test listing skills."""
    client = AgentTestClient(simple_agent)
    skills = client.list_skills()
    assert "add" in skills
    assert "greet" in skills
    assert "get_dict" in skills


def test_test_client_get_agent_card(simple_agent):
    """Test fetching agent card."""
    client = AgentTestClient(simple_agent)
    card = client.get_agent_card()
    assert card["name"] == "TestAgent"
    assert len(card["skills"]) == 3
