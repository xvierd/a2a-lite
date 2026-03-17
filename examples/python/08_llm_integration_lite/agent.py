"""
LLM Agent - A2A Lite Implementation

Advanced LLM-powered agent with minimal boilerplate.
Compare this ~90 line implementation with the ~686 line Google SDK version.
"""

import os
from a2a_lite import Agent
from a2a_lite.llm import OpenAIClient, AnthropicClient
from a2a_lite.tools import tool_registry

# Import tools (they auto-register via @tool decorator)
import tools  # noqa: F401

# Choose LLM provider
PROVIDER = os.getenv("LLM_PROVIDER", "openai")

if PROVIDER == "openai":
    llm_client = OpenAIClient(
        api_key=os.getenv("OPENAI_API_KEY"),
        model=os.getenv("LLM_MODEL", "gpt-4")
    )
else:
    llm_client = AnthropicClient(
        api_key=os.getenv("ANTHROPIC_API_KEY"),
        model=os.getenv("LLM_MODEL", "claude-3-sonnet-20240229")
    )

# Create LLM agent
# A2A Lite handles: memory, tool calling, context management
agent = Agent(
    name="LLMAgent",
    description="AI assistant with memory and tools",
    llm=llm_client,
    conversation_memory=True,  # Enable session memory
    tools=tool_registry.get_tools()  # Auto-registered tools
)


@agent.skill("chat")
async def chat(message: str, session_id: str = "default") -> dict:
    """
    Chat with the AI assistant.
    
    A2A Lite automatically:
    - Maintains conversation history per session_id
    - Calls tools when needed
    - Manages LLM context window
    """
    # Just return the user message - LLM handling is automatic!
    # The actual LLM response is handled by A2A Lite's LLM integration
    return {
        "message": message,
        "session_id": session_id,
        "note": "LLM response handled automatically by A2A Lite"
    }


@agent.skill("clear_memory")
async def clear_memory(session_id: str = "default") -> dict:
    """Clear conversation memory for a session."""
    # A2A Lite provides memory management
    agent.clear_conversation(session_id)
    return {"message": "Memory cleared", "session_id": session_id}


@agent.skill("info")
async def info() -> dict:
    """Get agent information."""
    return {
        "name": "LLMAgent",
        "provider": PROVIDER,
        "model": llm_client.model,
        "tools_available": [t.name for t in tool_registry.get_tools()],
        "features": ["memory", "tool_calling", "multi_turn"]
    }


if __name__ == "__main__":
    print("=" * 70)
    print("LLM Agent - A2A Lite (Advanced)")
    print("=" * 70)
    print(f"Provider: {PROVIDER}")
    print(f"Model: {llm_client.model}")
    print(f"Port: 8792")
    print("-" * 70)
    print("A2A Lite automatically handles:")
    print("  ✓ Conversation memory (per session)")
    print("  ✓ Tool registration (@tool decorator)")
    print("  ✓ LLM context management")
    print("  ✓ Multi-turn conversations")
    print("  ✓ Tool calling loop")
    print("-" * 70)
    print("Available tools:")
    for tool in tool_registry.get_tools():
        print(f"  - {tool.name}: {tool.description}")
    print("=" * 70)
    
    agent.run(port=8792)
