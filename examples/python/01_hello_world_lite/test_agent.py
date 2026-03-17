"""
Unit tests for the Hello Agent.

Demonstrates A2A Lite's built-in TestClient which allows testing
without starting an HTTP server.
"""

import pytest
from agent import agent
from a2a_lite import AgentTestClient


def test_greet_skill():
    """Test the greet skill directly."""
    client = AgentTestClient(agent)
    
    # Call the skill
    result = client.call("greet", name="World")
    
    # Verify result
    assert result == "Hello, World!"


def test_greet_with_different_names():
    """Test greet skill with various names."""
    client = AgentTestClient(agent)
    
    test_cases = [
        ("Alice", "Hello, Alice!"),
        ("Bob", "Hello, Bob!"),
        ("", "Hello, !"),  # Edge case: empty string
    ]
    
    for name, expected in test_cases:
        result = client.call("greet", name=name)
        assert result == expected


def test_list_skills():
    """Test that agent exposes the greet skill."""
    client = AgentTestClient(agent)
    
    skills = client.list_skills()
    
    assert "greet" in skills


def test_get_agent_card():
    """Test agent card generation."""
    client = AgentTestClient(agent)
    
    card = client.get_agent_card()
    
    assert card["name"] == "HelloAgent"
    assert card["description"] == "A simple greeting agent using A2A Lite"
    assert "greet" in [s["name"] for s in card["skills"]]


if __name__ == "__main__":
    print("Running tests...")
    test_greet_skill()
    print("✓ test_greet_skill passed")
    
    test_greet_with_different_names()
    print("✓ test_greet_with_different_names passed")
    
    test_list_skills()
    print("✓ test_list_skills passed")
    
    test_get_agent_card()
    print("✓ test_get_agent_card passed")
    
    print("\nAll tests passed! ✨")
