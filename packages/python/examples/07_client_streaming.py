"""
Example: Client-side SSE streaming consumption.

Demonstrates one agent consuming a streaming response from another agent over HTTP.
The StoryAgent streams story chunks word by word, and the DisplayAgent
consumes them in real-time using `delegate(..., stream=True)`.

Run:
    # Terminal 1 - Start the streaming story agent:
    python examples/07_client_streaming.py story

    # Terminal 2 - Start the display agent that consumes the stream:
    python examples/07_client_streaming.py display

    # Terminal 3 - Call the display agent:
    curl -X POST http://localhost:8788 -H "Content-Type: application/json" -d '{
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": "1",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": "{\"skill\": \"display_story\", \"params\": {\"topic\": \"a brave robot\"}}"}],
                "messageId": "msg-1"
            }
        }
    }'
"""
import asyncio
import sys

from a2a_lite import Agent, AgentNetwork


def create_story_agent():
    """A streaming agent that tells stories word by word."""
    agent = Agent(
        name="StoryAgent",
        description="Tells stories with streaming output",
    )

    @agent.skill("tell_story", streaming=True, description="Tell a short story about a topic")
    async def tell_story(topic: str):
        words = (
            f"Once upon a time, there was {topic}. "
            f"It went on an amazing adventure through the digital world. "
            f"Along the way, {topic} discovered the power of streaming. "
            f"And they all lived happily ever after. The End."
        ).split()

        for word in words:
            yield word + " "
            await asyncio.sleep(0.1)

    return agent


def create_display_agent():
    """An agent that consumes streaming responses from StoryAgent."""
    network = AgentNetwork()
    network.add("story", "http://localhost:8787")

    agent = Agent(
        name="DisplayAgent",
        description="Displays stories by streaming from StoryAgent",
        network=network,
    )

    @agent.skill("display_story", description="Stream a story from StoryAgent and display it")
    async def display_story(topic: str) -> str:
        collected = []

        # Use stream=True to consume SSE chunks from the remote agent
        async for chunk in await agent.delegate("story", "tell_story", stream=True, topic=topic):
            print(chunk, end="", flush=True)
            collected.append(chunk)

        print()  # newline at end
        return "".join(collected)

    return agent


if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "story"

    if role == "story":
        print("Starting StoryAgent on port 8787...")
        create_story_agent().run(port=8787)
    elif role == "display":
        print("Starting DisplayAgent on port 8788...")
        create_display_agent().run(port=8788)
    else:
        print(f"Unknown role: {role}. Use 'story' or 'display'.")
