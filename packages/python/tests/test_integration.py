"""
Integration tests using httpx to test running agents.
"""
import pytest
import json
from uuid import uuid4

from a2a_lite import Agent


@pytest.fixture
def calculator_agent():
    """Create a calculator agent for testing."""
    agent = Agent(name="Calculator", description="Math operations")

    @agent.skill("add")
    async def add(a: float, b: float) -> float:
        return a + b

    @agent.skill("multiply")
    async def multiply(a: float, b: float) -> float:
        return a * b

    return agent


@pytest.fixture
def greeting_agent():
    """Create a greeting agent for testing."""
    agent = Agent(name="Greeter", description="Greeting service")

    @agent.skill("greet")
    async def greet(name: str = "World") -> str:
        return f"Hello, {name}!"

    return agent


def test_agent_card_generation(calculator_agent):
    """Test that agent card is generated correctly."""
    card = calculator_agent.build_agent_card("localhost", 8787)

    assert card.name == "Calculator"
    assert card.description == "Math operations"
    assert len(card.skills) == 2

    skill_names = [s.name for s in card.skills]
    assert "add" in skill_names
    assert "multiply" in skill_names


def test_get_app(calculator_agent):
    """Test that get_app returns a Starlette app."""
    app = calculator_agent.get_app()

    # Should be a Starlette app
    assert hasattr(app, "routes")


@pytest.mark.asyncio
async def test_agent_card_endpoint(calculator_agent):
    """Test that agent card is served correctly."""
    from starlette.testclient import TestClient

    app = calculator_agent.get_app()
    client = TestClient(app)

    response = client.get("/.well-known/agent.json")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Calculator"
    assert len(data["skills"]) == 2


@pytest.mark.asyncio
async def test_skill_invocation(calculator_agent):
    """Test invoking a skill via HTTP."""
    from starlette.testclient import TestClient

    app = calculator_agent.get_app()
    client = TestClient(app)

    # Build A2A request
    message = json.dumps({"skill": "add", "params": {"a": 5, "b": 3}})
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

    response = client.post("/", json=request_body)
    assert response.status_code == 200

    data = response.json()
    # Response should contain result
    assert "result" in data or "error" not in data


@pytest.mark.asyncio
async def test_unknown_skill(calculator_agent):
    """Test calling an unknown skill."""
    from starlette.testclient import TestClient

    app = calculator_agent.get_app()
    client = TestClient(app)

    message = json.dumps({"skill": "unknown_skill", "params": {}})
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

    response = client.post("/", json=request_body)
    assert response.status_code == 200
    # Should still return 200 but with error in result


@pytest.mark.asyncio
async def test_greeting_skill(greeting_agent):
    """Test greeting agent."""
    from starlette.testclient import TestClient

    app = greeting_agent.get_app()
    client = TestClient(app)

    message = json.dumps({"skill": "greet", "params": {"name": "Alice"}})
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

    response = client.post("/", json=request_body)
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_default_parameter(greeting_agent):
    """Test skill with default parameter."""
    from starlette.testclient import TestClient

    app = greeting_agent.get_app()
    client = TestClient(app)

    # Call without 'name' parameter - should use default
    message = json.dumps({"skill": "greet", "params": {}})
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

    response = client.post("/", json=request_body)
    assert response.status_code == 200


def test_error_handler():
    """Test custom error handler."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("fail")
    async def fail() -> str:
        raise ValueError("Intentional failure")

    @agent.on_error
    async def handle_error(error):
        return {"custom_error": str(error), "handled": True}

    assert agent._error_handler is not None


def test_multiple_agents():
    """Test creating multiple independent agents."""
    agent1 = Agent(name="Agent1", description="First agent")
    agent2 = Agent(name="Agent2", description="Second agent")

    @agent1.skill("skill1")
    async def skill1() -> str:
        return "from agent1"

    @agent2.skill("skill2")
    async def skill2() -> str:
        return "from agent2"

    assert "skill1" in agent1._skills
    assert "skill2" not in agent1._skills
    assert "skill2" in agent2._skills
    assert "skill1" not in agent2._skills
