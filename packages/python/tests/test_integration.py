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


def test_sync_skill_via_http():
    """Test that sync skills work via HTTP."""
    from starlette.testclient import TestClient

    agent = Agent(name="SyncTest", description="Sync skill test")

    @agent.skill("double")
    def double(x: int) -> int:
        return x * 2

    app = agent.get_app()
    client = TestClient(app)

    message = json.dumps({"skill": "double", "params": {"x": 21}})
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
    result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
    assert "42" in result_text


def test_skill_returning_dict_via_http():
    """Test skill returning dict via HTTP."""
    from starlette.testclient import TestClient

    agent = Agent(name="DictTest", description="Dict result test")

    @agent.skill("info")
    async def info(name: str) -> dict:
        return {"name": name, "status": "active"}

    app = agent.get_app()
    client = TestClient(app)

    message = json.dumps({"skill": "info", "params": {"name": "Alice"}})
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
    result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
    result = json.loads(result_text)
    assert result["name"] == "Alice"
    assert result["status"] == "active"


def test_skill_returning_list_via_http():
    """Test skill returning list via HTTP."""
    from starlette.testclient import TestClient

    agent = Agent(name="ListTest", description="List result test")

    @agent.skill("numbers")
    async def numbers(n: int) -> list:
        return list(range(n))

    app = agent.get_app()
    client = TestClient(app)

    message = json.dumps({"skill": "numbers", "params": {"n": 5}})
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
    result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
    result = json.loads(result_text)
    assert result == [0, 1, 2, 3, 4]


def test_error_handler_via_http():
    """Test that custom error handler is called via HTTP."""
    from starlette.testclient import TestClient

    agent = Agent(name="ErrorTest", description="Error handler test")

    @agent.skill("fail")
    async def fail() -> str:
        raise ValueError("Intentional error")

    @agent.on_error
    async def handle_error(error):
        return {"handled": True, "error_type": type(error).__name__}

    app = agent.get_app()
    client = TestClient(app)

    message = json.dumps({"skill": "fail", "params": {}})
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
    result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
    result = json.loads(result_text)
    assert result["handled"] is True


def test_middleware_via_http():
    """Test middleware execution via HTTP."""
    from starlette.testclient import TestClient
    from a2a_lite.middleware import timing_middleware

    agent = Agent(name="MWTest", description="Middleware test")
    agent.add_middleware(timing_middleware())

    @agent.skill("hello")
    async def hello(name: str = "World") -> str:
        return f"Hello, {name}!"

    app = agent.get_app()
    client = TestClient(app)

    message = json.dumps({"skill": "hello", "params": {"name": "Test"}})
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
    result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
    assert "Hello, Test!" in result_text


def test_plain_text_message():
    """Test sending a plain text (non-JSON) message to an agent."""
    from starlette.testclient import TestClient

    agent = Agent(name="PlainTest", description="Plain text test")

    @agent.skill("echo")
    async def echo(message: str) -> str:
        return f"Echo: {message}"

    app = agent.get_app()
    client = TestClient(app)

    # Send plain text instead of JSON skill call
    request_body = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": uuid4().hex,
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Hello there"}],
                "messageId": uuid4().hex,
            }
        }
    }

    response = client.post("/", json=request_body)
    assert response.status_code == 200


def test_pydantic_model_via_http():
    """Test Pydantic model parameter via HTTP."""
    from starlette.testclient import TestClient
    from pydantic import BaseModel

    class UserInput(BaseModel):
        name: str
        age: int

    agent = Agent(name="PydanticHTTP", description="Pydantic HTTP test")

    @agent.skill("create_user")
    async def create_user(user: UserInput) -> dict:
        return {"created": True, "name": user.name, "age": user.age}

    app = agent.get_app()
    client = TestClient(app)

    message = json.dumps({
        "skill": "create_user",
        "params": {"user": {"name": "Alice", "age": 30}},
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

    response = client.post("/", json=request_body)
    assert response.status_code == 200

    data = response.json()
    result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
    result = json.loads(result_text)
    assert result["created"] is True
    assert result["name"] == "Alice"


def test_agent_with_no_skills():
    """Test agent with no skills registered."""
    from starlette.testclient import TestClient

    agent = Agent(name="EmptyAgent", description="No skills")
    app = agent.get_app()
    client = TestClient(app)

    message = json.dumps({"skill": "nonexistent", "params": {}})
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


def test_completion_hook_via_http():
    """Test that completion hooks are called."""
    from starlette.testclient import TestClient

    completed_skills = []
    agent = Agent(name="HookTest", description="Hook test")

    @agent.skill("hello")
    async def hello() -> str:
        return "world"

    @agent.on_complete
    async def on_complete(skill_name, result, ctx):
        completed_skills.append(skill_name)

    app = agent.get_app()
    client = TestClient(app)

    message = json.dumps({"skill": "hello", "params": {}})
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
    assert "hello" in completed_skills


def test_single_skill_auto_dispatch():
    """Test that a single-skill agent auto-dispatches plain text."""
    from starlette.testclient import TestClient

    agent = Agent(name="SingleSkill", description="One skill")

    @agent.skill("echo")
    async def echo(message: str) -> str:
        return f"Echo: {message}"

    app = agent.get_app()
    client = TestClient(app)

    # Send plain text — should auto-dispatch to the only skill
    request_body = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": uuid4().hex,
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "Hello there"}],
                "messageId": uuid4().hex,
            }
        }
    }

    response = client.post("/", json=request_body)
    assert response.status_code == 200

    data = response.json()
    result_text = data.get("result", {}).get("parts", [{}])[0].get("text", "")
    assert "Echo:" in result_text
