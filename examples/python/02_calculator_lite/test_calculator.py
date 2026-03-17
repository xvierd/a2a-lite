"""
Unit tests for Calculator Agent using A2A Lite's TestClient.

These tests run without starting an HTTP server, making them
much faster than integration tests.
"""

import pytest
from agent import agent
from a2a_lite import AgentTestClient


@pytest.fixture
def client():
    """Create a test client for the agent."""
    return AgentTestClient(agent)


def test_add(client):
    """Test addition skill."""
    result = client.call("add", a=10, b=5)
    assert result.data["result"] == 15


def test_subtract(client):
    """Test subtraction skill."""
    result = client.call("subtract", a=10, b=3)
    assert result.data["result"] == 7


def test_multiply(client):
    """Test multiplication skill."""
    result = client.call("multiply", a=6, b=7)
    assert result.data["result"] == 42


def test_divide(client):
    """Test division skill."""
    result = client.call("divide", a=10, b=3)
    assert abs(result.data["result"] - 3.333) < 0.01
    assert result.data["remainder"] == 1


def test_divide_by_zero(client):
    """Test division by zero error handling."""
    with pytest.raises(Exception) as exc_info:
        client.call("divide", a=10, b=0)
    assert "Division by zero" in str(exc_info.value)


def test_power(client):
    """Test power skill."""
    result = client.call("power", base=2, exponent=10)
    assert result.data["result"] == 1024


def test_list_skills(client):
    """Test that all skills are registered."""
    skills = client.list_skills()
    
    expected_skills = ["add", "subtract", "multiply", "divide", "power"]
    for skill in expected_skills:
        assert skill in skills


def test_agent_card(client):
    """Test agent card generation."""
    card = client.get_agent_card()
    
    assert card["name"] == "CalculatorAgent"
    assert card["description"] == "A calculator agent with arithmetic operations"
    assert len(card["skills"]) == 5


def test_unknown_skill(client):
    """Test calling unknown skill."""
    with pytest.raises(Exception) as exc_info:
        client.call("unknown", a=1, b=2)
    assert "not found" in str(exc_info.value).lower()


if __name__ == "__main__":
    print("Running Calculator Agent tests...")
    
    client = AgentTestClient(agent)
    
    tests = [
        test_add,
        test_subtract,
        test_multiply,
        test_divide,
        test_divide_by_zero,
        test_power,
        test_list_skills,
        test_agent_card,
        test_unknown_skill,
    ]
    
    for test in tests:
        try:
            test(client)
            print(f"✓ {test.__name__}")
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
    
    print("\nAll tests completed!")
