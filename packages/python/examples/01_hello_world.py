"""
Simplest possible A2A Lite agent.

Run with: python examples/01_hello_world.py
Test with: a2a-lite test http://localhost:8787 greet -p name=World
"""
from a2a_lite import Agent

agent = Agent(
    name="HelloWorld",
    description="A simple greeting agent",
)


@agent.skill("greet", description="Greet someone by name")
async def greet(name: str = "World") -> str:
    return f"Hello, {name}!"


if __name__ == "__main__":
    agent.run(port=8787)
