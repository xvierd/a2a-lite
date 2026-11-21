"""
Calculator agent with multiple skills.

Run with: python examples/02_calculator.py
Test with: a2a-lite test http://localhost:8787 add -p a=5 -p b=3

From an A2A client such as Google ADK, send "What can you calculate?"
in a text part to get help. To invoke a particular skill, send the text
'{"skill":"add","params":{"a":5,"b":3}}'. For an unknown skill the agent
returns a message whose text decodes to a JSON object. Read its
`available_skills` list to choose a skill and try again.
"""

from a2a_lite import Agent

agent = Agent(
    name="Calculator",
    description="Performs mathematical operations",
    version="1.0.0",
    free_text_skill="help",
)


@agent.skill("help", description="Explain how to use the calculator")
async def calculator_help(message: str) -> str:
    return 'Send a calculation such as {"skill":"add","params":{"a":5,"b":3}}.'


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
