"""
Calculator agent with multiple skills.

Run with: python examples/02_calculator.py
Test with: a2a-lite test http://localhost:8787 add -p a=5 -p b=3
"""
from a2a_lite import Agent

agent = Agent(
    name="Calculator",
    description="Performs mathematical operations",
    version="1.0.0",
)


@agent.skill("add", description="Add two numbers")
async def add(a: float, b: float) -> float:
    return a + b


@agent.skill("subtract", description="Subtract b from a")
async def subtract(a: float, b: float) -> float:
    return a - b


@agent.skill("multiply", description="Multiply two numbers")
async def multiply(a: float, b: float) -> float:
    return a * b


@agent.skill("divide", description="Divide a by b")
async def divide(a: float, b: float) -> dict:
    if b == 0:
        return {"error": "Cannot divide by zero"}
    return {"result": a / b}


@agent.on_error
async def handle_error(error: Exception):
    return {
        "error": str(error),
        "type": type(error).__name__,
        "hint": "Check your input parameters",
    }


if __name__ == "__main__":
    agent.run(port=8787)
