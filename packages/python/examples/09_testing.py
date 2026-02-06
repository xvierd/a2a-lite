"""
Example: Testing your agents.

A2A Lite includes a TestClient that makes testing trivial.

Run: python examples/09_testing.py
"""
from a2a_lite import Agent, AgentTestClient


# Create a simple agent
agent = Agent(name="Calculator", description="Math operations")


@agent.skill("add")
async def add(a: int, b: int) -> int:
    return a + b


@agent.skill("multiply")
async def multiply(a: int, b: int) -> int:
    return a * b


@agent.skill("divide")
async def divide(a: float, b: float) -> dict:
    if b == 0:
        return {"error": "Cannot divide by zero"}
    return {"result": a / b}


# Testing is this simple:
def test_add():
    client = AgentTestClient(agent)
    result = client.call("add", a=2, b=3)
    assert result == 5
    print("✅ test_add passed")


def test_multiply():
    client = AgentTestClient(agent)
    result = client.call("multiply", a=4, b=5)
    assert result == 20
    print("✅ test_multiply passed")


def test_divide():
    client = AgentTestClient(agent)
    result = client.call("divide", a=10, b=2)
    assert result.data["result"] == 5.0
    print("✅ test_divide passed")


def test_divide_by_zero():
    client = AgentTestClient(agent)
    result = client.call("divide", a=10, b=0)
    assert "error" in result.data
    print("✅ test_divide_by_zero passed")


def test_list_skills():
    client = AgentTestClient(agent)
    skills = client.list_skills()
    assert "add" in skills
    assert "multiply" in skills
    assert "divide" in skills
    print("✅ test_list_skills passed")


if __name__ == "__main__":
    # Run all tests
    print("Running tests...\n")

    test_add()
    test_multiply()
    test_divide()
    test_divide_by_zero()
    test_list_skills()

    print("\n🎉 All tests passed!")

    # Optionally run the server
    # agent.run(port=8787)
