"""
Example 16: Anthropic-Powered Agent

Demonstrates using the anthropic_skill decorator for Claude-powered skills.

Prerequisites:
    pip install a2a-lite[anthropic]
    export ANTHROPIC_API_KEY=your-key-here

Run:
    python examples/16_llm_anthropic.py
"""
from a2a_lite import Agent
from a2a_lite.llm import anthropic_skill

agent = Agent(
    name="Claude Agent",
    description="An agent powered by Anthropic's Claude",
    version="1.0.0",
)


@agent.skill("analyze", description="Analyze text with Claude")
@anthropic_skill(
    model="claude-sonnet-4-5-20250929",
    system_prompt="You are an expert analyst. Provide clear, structured analysis.",
    max_tokens=1024,
)
async def analyze(text: str) -> str:
    """Analyze the provided text using Claude."""
    ...  # Handled by the anthropic_skill decorator


@agent.skill("code_review", description="Review code with Claude")
@anthropic_skill(
    model="claude-sonnet-4-5-20250929",
    system_prompt=(
        "You are an expert code reviewer. Review the code for bugs, "
        "security issues, and style. Be concise."
    ),
    max_tokens=2048,
    temperature=0.3,
)
async def code_review(text: str) -> str:
    """Review code and provide feedback."""
    ...  # Handled by the anthropic_skill decorator


@agent.skill("chat", description="Chat with Claude (streaming)", streaming=True)
@anthropic_skill(
    model="claude-sonnet-4-5-20250929",
    system_prompt="You are a helpful, friendly assistant.",
    streaming=True,
)
async def chat(message: str) -> str:
    """Stream a conversation with Claude."""
    ...  # Handled by the anthropic_skill decorator


if __name__ == "__main__":
    agent.run(port=8787)
