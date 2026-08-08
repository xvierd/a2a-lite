"""
LLM Agent - A2A Lite Implementation

LLM-powered agent with minimal boilerplate using A2A Lite's LLM decorators.
Compare this ~60 line implementation with the ~350 line Google SDK version.

Requires (only at call time, not import time):
    pip install a2a-lite[openai]     # if LLM_PROVIDER=openai (default)
    pip install a2a-lite[anthropic]  # if LLM_PROVIDER=anthropic

Environment:
    LLM_PROVIDER   openai (default) | anthropic
    LLM_MODEL      e.g. gpt-4o-mini (default) or claude-3-haiku-20240307
    OPENAI_API_KEY / ANTHROPIC_API_KEY  (read by the provider SDK itself)
"""

import os
from a2a_lite import Agent
from a2a_lite.llm import openai_skill, anthropic_skill

# Choose LLM provider
PROVIDER = os.getenv("LLM_PROVIDER", "openai")
MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini" if PROVIDER == "openai" else "claude-3-haiku-20240307")

# Create the agent - no llm/memory/tool plumbing needed
agent = Agent(
    name="LLMAgent",
    description="AI assistant powered by an LLM",
    version="1.0.0",
)

# Pick the decorator for the configured provider.
# The provider package (openai/anthropic) is imported lazily on first call.
if PROVIDER == "openai":
    llm = openai_skill(
        model=MODEL,
        system_prompt="You are a helpful AI assistant exposed via the A2A protocol.",
    )
else:
    llm = anthropic_skill(
        model=MODEL,
        system_prompt="You are a helpful AI assistant exposed via the A2A protocol.",
    )


@agent.skill("chat")
@llm
async def chat(message: str) -> str:
    """
    Chat with the AI assistant.

    The decorator handles the whole LLM call: the `message` parameter is
    sent as the user message and the LLM's text is returned as the result.
    """
    ...  # handled by the llm decorator


@agent.skill("chat_stream", streaming=True)
@openai_skill(
    model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
    system_prompt="You are a helpful AI assistant exposed via the A2A protocol.",
    streaming=True,
)
async def chat_stream(message: str) -> str:
    """
    Streaming chat (OpenAI only): yields tokens as they arrive.

    Just add streaming=True to both decorators - A2A Lite handles SSE.
    """
    ...  # handled by the llm decorator


@agent.skill("info")
async def info() -> dict:
    """Get agent information."""
    return {
        "name": "LLMAgent",
        "provider": PROVIDER,
        "model": MODEL,
        "skills": ["chat", "chat_stream", "info"],
        "features": ["llm_decorator", "streaming"],
        "note": "Set OPENAI_API_KEY or ANTHROPIC_API_KEY to enable chat.",
    }


if __name__ == "__main__":
    print("=" * 70)
    print("LLM Agent - A2A Lite (Advanced)")
    print("=" * 70)
    print(f"Provider: {PROVIDER}")
    print(f"Model: {MODEL}")
    print(f"Port: 8792")
    print("-" * 70)
    print("A2A Lite handles:")
    print("  ✓ LLM call via @openai_skill / @anthropic_skill decorators")
    print("  ✓ Token streaming (streaming=True)")
    print("  ✓ SSE protocol formatting")
    print("-" * 70)
    print("Skills:")
    print("  - chat:        Single-shot LLM chat (configured provider)")
    print("  - chat_stream: Token-by-token streaming chat (OpenAI)")
    print("  - info:        Agent configuration")
    print("=" * 70)

    agent.run(port=8792)
