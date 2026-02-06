"""
Example: Streaming responses (like ChatGPT).

Use `yield` to stream chunks to the client in real-time.

Run: python examples/08_streaming.py
"""
import asyncio
from a2a_lite import Agent


agent = Agent(
    name="StreamingDemo",
    description="Shows streaming responses",
)


@agent.skill("count", streaming=True, description="Count from 1 to n with delay")
async def count(n: int = 5, delay: float = 0.5):
    """
    Stream numbers one at a time.
    Just use `yield` - A2A Lite handles the rest!
    """
    for i in range(1, n + 1):
        yield f"Count: {i}\n"
        await asyncio.sleep(delay)
    yield "Done!"


@agent.skill("typewriter", streaming=True, description="Type out a message slowly")
async def typewriter(message: str, delay: float = 0.05):
    """Stream each character like a typewriter."""
    for char in message:
        yield char
        await asyncio.sleep(delay)


@agent.skill("fake_llm", streaming=True, description="Simulate LLM streaming")
async def fake_llm(prompt: str):
    """
    Simulates an LLM streaming response.
    In real use, you'd yield chunks from your LLM.
    """
    words = f"You asked: {prompt}. Here is my response word by word.".split()

    for word in words:
        yield word + " "
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    agent.run(port=8787)
