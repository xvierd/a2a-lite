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
