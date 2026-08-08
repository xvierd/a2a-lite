"""
Hello Agent - A2A Lite Implementation

The simplest possible A2A agent. Just 8 lines of code for a fully
protocol-compliant agent with auto-generated schemas and discovery.
"""

from a2a_lite import Agent

# Create the agent
agent = Agent(
    name="HelloAgent",
    description="A simple greeting agent using A2A Lite"
)

# Define a skill using the decorator
@agent.skill("greet")
async def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


if __name__ == "__main__":
    print("=" * 60)
    print("Hello Agent - A2A Lite")
    print("=" * 60)
    print("Agent: HelloAgent")
    print("Skills: greet")
    print("-" * 60)
    print("Starting server on http://localhost:8787")
    print("Agent card: http://localhost:8787/.well-known/agent-card.json")
    print("=" * 60)
    
    # Run the agent
    agent.run()
