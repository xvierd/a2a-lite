"""
Calculator Agent - A2A Lite Implementation

A multi-skill calculator demonstrating A2A Lite's decorator-based API.
Compare this ~40 line implementation with the ~220 line Google SDK version.
"""

from a2a_lite import Agent

# Create the calculator agent
agent = Agent(
    name="CalculatorAgent",
    description="A calculator agent with arithmetic operations",
    version="1.0.0"
)


@agent.skill("add")
async def add(a: float, b: float) -> dict:
    """Add two numbers."""
    return {"result": a + b}


@agent.skill("subtract")
async def subtract(a: float, b: float) -> dict:
    """Subtract b from a."""
    return {"result": a - b}


@agent.skill("multiply")
async def multiply(a: float, b: float) -> dict:
    """Multiply two numbers."""
    return {"result": a * b}


@agent.skill("divide")
async def divide(a: float, b: float) -> dict:
    """
    Divide a by b.
    
    Raises:
        ValueError: If b is zero (automatically converted to A2A error)
    """
    if b == 0:
        raise ValueError("Division by zero is not allowed")
    return {
        "result": a / b,
        "remainder": a % b
    }


@agent.skill("power")
async def power(base: float, exponent: float) -> dict:
    """Raise base to the power of exponent."""
    return {"result": base ** exponent}


if __name__ == "__main__":
    print("=" * 60)
    print("Calculator Agent - A2A Lite")
    print("=" * 60)
    print("Agent: CalculatorAgent")
    print("Skills: add, subtract, multiply, divide, power")
    print("-" * 60)
    print("Starting server on http://localhost:8788")
    print("Agent card: http://localhost:8788/.well-known/agent.json")
    print("=" * 60)
    
    agent.run(port=8788)
