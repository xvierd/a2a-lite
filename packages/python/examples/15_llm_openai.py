"""
Example 15: OpenAI-Powered Agent with Streaming

Demonstrates using the openai_skill decorator for LLM-powered skills.
Supports both streaming (token-by-token) and non-streaming modes.

Prerequisites:
    pip install a2a-lite[openai]
    export OPENAI_API_KEY=your-key-here

Run:
    python examples/15_llm_openai.py
"""
from a2a_lite import Agent
from a2a_lite.llm import openai_skill

agent = Agent(
    name="OpenAI Agent",
    description="An agent powered by OpenAI models",
    version="1.0.0",
)


@agent.skill("chat", description="Chat with GPT (streaming)", streaming=True)
@openai_skill(
    model="gpt-4o-mini",
    system_prompt="You are a helpful, concise assistant.",
    streaming=True,
)
async def chat(message: str) -> str:
    """Chat with the AI. Streams tokens as they're generated."""
    ...  # Handled by the openai_skill decorator


@agent.skill("summarize", description="Summarize text")
@openai_skill(
    model="gpt-4o-mini",
    system_prompt="You are an expert summarizer. Provide concise summaries in 2-3 sentences.",
    temperature=0.3,
)
async def summarize(text: str) -> str:
    """Summarize the provided text."""
    ...  # Handled by the openai_skill decorator


@agent.skill("translate", description="Translate text to another language")
@openai_skill(
    model="gpt-4o-mini",
    system_prompt="You are a translator. Translate the user's text to the language they specify. Only output the translation.",
    temperature=0.2,
)
async def translate(text: str) -> str:
    """Translate text. Include the target language in your message, e.g., 'Translate to French: Hello'."""
    ...  # Handled by the openai_skill decorator


if __name__ == "__main__":
    agent.run(port=8787)
