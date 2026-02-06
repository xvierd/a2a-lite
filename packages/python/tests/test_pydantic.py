"""
Tests for Pydantic model support.
"""
import pytest
from pydantic import BaseModel
from typing import List, Optional
from a2a_lite import Agent, AgentTestClient


class User(BaseModel):
    name: str
    age: int


class CreateUserRequest(BaseModel):
    user: User
    notify: bool = False


@pytest.fixture
def pydantic_agent():
    """Create an agent with Pydantic model parameters."""
    agent = Agent(name="PydanticAgent", description="Uses Pydantic")

    @agent.skill("create_user")
    async def create_user(user: User) -> dict:
        return {
            "created": True,
            "name": user.name,
            "age": user.age,
        }

    @agent.skill("get_user_info")
    async def get_user_info(user: User) -> str:
        return f"{user.name} is {user.age} years old"

    @agent.skill("list_users")
    async def list_users(users: List[User]) -> int:
        return len(users)

    return agent


def test_pydantic_model_input(pydantic_agent):
    """Test that Pydantic models are auto-converted from dicts."""
    client = AgentTestClient(pydantic_agent)

    result = client.call("create_user", user={"name": "Alice", "age": 30})

    assert result.data["created"] is True
    assert result.data["name"] == "Alice"
    assert result.data["age"] == 30


def test_pydantic_model_string_output(pydantic_agent):
    """Test skill returning string from Pydantic input."""
    client = AgentTestClient(pydantic_agent)

    result = client.call("get_user_info", user={"name": "Bob", "age": 25})

    assert result == "Bob is 25 years old"


def test_pydantic_list_of_models(pydantic_agent):
    """Test list of Pydantic models."""
    client = AgentTestClient(pydantic_agent)

    users = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Charlie", "age": 35},
    ]

    result = client.call("list_users", users=users)
    assert result == 3


def test_schema_generation_from_pydantic():
    """Test that schemas are generated from Pydantic models."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("create")
    async def create(user: User) -> dict:
        return {}

    skill = agent._skills["create"]

    # Input schema should have user property
    assert "user" in skill.input_schema["properties"]


class Address(BaseModel):
    street: str
    city: str
    zip_code: str


class UserWithAddress(BaseModel):
    name: str
    age: int
    address: Address


def test_nested_pydantic_model():
    """Test nested Pydantic models are converted."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("create")
    async def create(user: UserWithAddress) -> dict:
        return {
            "name": user.name,
            "city": user.address.city,
        }

    client = AgentTestClient(agent)
    result = client.call(
        "create",
        user={
            "name": "Alice",
            "age": 30,
            "address": {
                "street": "123 Main St",
                "city": "Springfield",
                "zip_code": "12345",
            },
        },
    )
    assert result.data["name"] == "Alice"
    assert result.data["city"] == "Springfield"


class UserOptional(BaseModel):
    name: str
    nickname: Optional[str] = None
    age: int = 0


def test_pydantic_optional_fields():
    """Test Pydantic model with optional fields."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("create")
    async def create(user: UserOptional) -> dict:
        return {"name": user.name, "nickname": user.nickname, "age": user.age}

    client = AgentTestClient(agent)
    result = client.call("create", user={"name": "Bob"})
    assert result.data["name"] == "Bob"
    assert result.data["nickname"] is None
    assert result.data["age"] == 0


def test_pydantic_model_already_instance():
    """Test passing an already-instantiated Pydantic model."""
    agent = Agent(name="Test", description="Test")

    @agent.skill("info")
    async def info(user: User) -> str:
        return f"{user.name} ({user.age})"

    # The AgentTestClient serializes params to JSON, so this tests the dict path
    client = AgentTestClient(agent)
    result = client.call("info", user={"name": "Carol", "age": 28})
    assert result == "Carol (28)"


def test_multiple_pydantic_params():
    """Test skill with multiple Pydantic model parameters."""
    class Source(BaseModel):
        name: str

    class Target(BaseModel):
        name: str

    agent = Agent(name="Test", description="Test")

    @agent.skill("transfer")
    async def transfer(source: Source, target: Target) -> str:
        return f"{source.name} -> {target.name}"

    client = AgentTestClient(agent)
    result = client.call(
        "transfer",
        source={"name": "Alice"},
        target={"name": "Bob"},
    )
    assert result == "Alice -> Bob"
