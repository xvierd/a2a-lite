"""
Agent that uses an LLM for intelligent responses.
Supports OpenAI, Anthropic (via adapter), or any OpenAI-compatible API.

Run with:
  export OPENAI_API_KEY=your-key
  python examples/05_with_llm.py

Test with:
  a2a-lite test http://localhost:8787 chat -p message="What is Python?"
"""
import os
from typing import Optional
from a2a_lite import Agent

# Initialize OpenAI client if available
client = None
try:
    from openai import AsyncOpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        client = AsyncOpenAI(
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL"),  # For OpenRouter, local LLMs, etc.
        )
except ImportError:
    pass

agent = Agent(
    name="SmartAssistant",
    description="An AI-powered assistant using LLM",
)


@agent.skill("chat", description="Have a conversation with AI")
async def chat(message: str, context: Optional[str] = None) -> dict:
    """Chat with the AI assistant."""
    if not client:
        return {
            "error": "OpenAI client not configured",
            "hint": "Set OPENAI_API_KEY environment variable and install openai package",
        }

    system_prompt = "You are a helpful assistant. Be concise and direct."
    if context:
        system_prompt += f"\n\nContext: {context}"

    try:
        response = await client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            max_tokens=500,
        )

        return {
            "response": response.choices[0].message.content,
            "model": response.model,
            "tokens_used": response.usage.total_tokens if response.usage else None,
        }
    except Exception as e:
        return {
            "error": str(e),
            "type": type(e).__name__,
        }


@agent.skill("summarize", description="Summarize text")
async def summarize(text: str, max_words: int = 100) -> dict:
    """Summarize the provided text."""
    result = await chat(
        message=f"Summarize the following in {max_words} words or less:\n\n{text}",
    )

    if "error" in result:
        return result

    return {
        "original_length": len(text.split()),
        "summary": result.get("response", ""),
        "model": result.get("model"),
    }


@agent.skill("translate", description="Translate text to another language")
async def translate(text: str, target_language: str = "Spanish") -> dict:
    """Translate text to the target language."""
    result = await chat(
        message=f"Translate the following to {target_language}. Only provide the translation, no explanations:\n\n{text}",
    )

    if "error" in result:
        return result

    return {
        "original": text,
        "translated": result.get("response", ""),
        "target_language": target_language,
        "model": result.get("model"),
    }


@agent.skill("analyze_sentiment", description="Analyze sentiment of text")
async def analyze_sentiment(text: str) -> dict:
    """Analyze the sentiment of the provided text."""
    result = await chat(
        message=f"Analyze the sentiment of this text. Respond with JSON containing 'sentiment' (positive/negative/neutral), 'confidence' (0-1), and 'explanation':\n\n{text}",
    )

    if "error" in result:
        return result

    return {
        "text": text,
        "analysis": result.get("response", ""),
        "model": result.get("model"),
    }


if __name__ == "__main__":
    if not client:
        print("WARNING: OpenAI client not configured.")
        print("Set OPENAI_API_KEY environment variable to enable LLM features.")
        print("The agent will start but LLM skills will return errors.\n")

    agent.run(port=8787)
