"""
Example 17: AWS Bedrock-Powered Agent

Demonstrates using the bedrock_skill decorator for Bedrock-powered skills.
Works with any model available on Bedrock (Claude, Llama, Mistral, Nova, etc.)
via the model-agnostic Converse API.

Prerequisites:
    pip install a2a-lite[bedrock]
    AWS credentials configured (env vars, ~/.aws/credentials, or IAM role)

Run:
    python examples/17_llm_bedrock.py
"""
from a2a_lite import Agent
from a2a_lite.llm import bedrock_skill

agent = Agent(
    name="Bedrock Agent",
    description="An agent powered by AWS Bedrock",
    version="1.0.0",
)


@agent.skill("chat", description="Chat via Bedrock")
@bedrock_skill(
    model="anthropic.claude-3-haiku-20240307-v1:0",
    system_prompt="You are a helpful, friendly assistant.",
    max_tokens=1024,
)
async def chat(message: str) -> str:
    """Chat using a Bedrock model."""
    ...  # Handled by the bedrock_skill decorator


@agent.skill("summarize", description="Summarize text via Bedrock")
@bedrock_skill(
    model="anthropic.claude-3-haiku-20240307-v1:0",
    system_prompt="You are an expert summarizer. Provide clear, concise summaries.",
    max_tokens=512,
    temperature=0.3,
)
async def summarize(text: str) -> str:
    """Summarize the provided text."""
    ...  # Handled by the bedrock_skill decorator


@agent.skill("stream_chat", description="Stream chat via Bedrock", streaming=True)
@bedrock_skill(
    model="anthropic.claude-3-haiku-20240307-v1:0",
    system_prompt="You are a helpful assistant.",
    streaming=True,
)
async def stream_chat(message: str) -> str:
    """Stream a conversation with a Bedrock model."""
    ...  # Handled by the bedrock_skill decorator


if __name__ == "__main__":
    agent.run(port=8787)
