"""
LLM provider integration decorators for A2A Lite.

Provides decorators that wrap skills to call LLM APIs (OpenAI, Anthropic, Ollama).
Each uses optional import patterns — the LLM library is only required at runtime.

Requires:
    pip install a2a-lite[openai]     # for openai_skill
    pip install a2a-lite[anthropic]  # for anthropic_skill
    ollama_skill uses httpx (already a core dep)

Example:
    from a2a_lite.llm import openai_skill, anthropic_skill

    @agent.skill("chat", streaming=True)
    @openai_skill(model="gpt-4o-mini", system_prompt="You are helpful.")
    async def chat(message: str) -> str:
        ...  # handled by decorator

    @agent.skill("analyze")
    @anthropic_skill(model="claude-sonnet-4-5-20250929")
    async def analyze(text: str) -> str:
        ...  # handled by decorator
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Optional


def openai_skill(
    model: str = "gpt-4o-mini",
    system_prompt: str = "You are a helpful assistant.",
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    streaming: bool = False,
    **extra_kwargs: Any,
) -> Callable:
    """Decorator that wraps a skill to call the OpenAI chat completions API.

    The decorated function's first ``str`` parameter is used as the user
    message.  When ``streaming=True`` the wrapper becomes an async generator
    that yields tokens.

    Args:
        model: OpenAI model identifier.
        system_prompt: System message for the chat.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in the response.
        streaming: Whether to stream tokens.
        **extra_kwargs: Additional kwargs forwarded to the OpenAI client.

    Returns:
        A decorator that replaces the skill handler.

    Raises:
        ImportError: If the ``openai`` package is not installed.

    Example:
        @agent.skill("chat")
        @openai_skill(model="gpt-4o-mini")
        async def chat(message: str) -> str:
            ...
    """

    def decorator(func: Callable) -> Callable:
        if streaming:

            @functools.wraps(func)
            async def streaming_wrapper(**kwargs: Any):  # type: ignore[misc]
                try:
                    import openai
                except ImportError:
                    raise ImportError(
                        "OpenAI integration requires the 'openai' package. "
                        "Install it with: pip install a2a-lite[openai]"
                    )

                user_message = _extract_user_message(kwargs)
                client = openai.AsyncOpenAI(**extra_kwargs)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ]
                create_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "stream": True,
                }
                if max_tokens is not None:
                    create_kwargs["max_tokens"] = max_tokens

                stream = await client.chat.completions.create(**create_kwargs)
                async for chunk in stream:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if delta and delta.content:
                        yield delta.content

            return streaming_wrapper
        else:

            @functools.wraps(func)
            async def wrapper(**kwargs: Any) -> str:
                try:
                    import openai
                except ImportError:
                    raise ImportError(
                        "OpenAI integration requires the 'openai' package. "
                        "Install it with: pip install a2a-lite[openai]"
                    )

                user_message = _extract_user_message(kwargs)
                client = openai.AsyncOpenAI(**extra_kwargs)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ]
                create_kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_tokens is not None:
                    create_kwargs["max_tokens"] = max_tokens

                response = await client.chat.completions.create(**create_kwargs)
                return response.choices[0].message.content or ""

            return wrapper

    return decorator


def anthropic_skill(
    model: str = "claude-sonnet-4-5-20250929",
    system_prompt: str = "You are a helpful assistant.",
    temperature: float = 0.7,
    max_tokens: int = 1024,
    streaming: bool = False,
    **extra_kwargs: Any,
) -> Callable:
    """Decorator that wraps a skill to call the Anthropic messages API.

    Args:
        model: Anthropic model identifier.
        system_prompt: System message for the conversation.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in the response.
        streaming: Whether to stream tokens.
        **extra_kwargs: Additional kwargs forwarded to the Anthropic client.

    Returns:
        A decorator that replaces the skill handler.

    Raises:
        ImportError: If the ``anthropic`` package is not installed.

    Example:
        @agent.skill("analyze")
        @anthropic_skill(model="claude-sonnet-4-5-20250929")
        async def analyze(text: str) -> str:
            ...
    """

    def decorator(func: Callable) -> Callable:
        if streaming:

            @functools.wraps(func)
            async def streaming_wrapper(**kwargs: Any):  # type: ignore[misc]
                try:
                    import anthropic
                except ImportError:
                    raise ImportError(
                        "Anthropic integration requires the 'anthropic' package. "
                        "Install it with: pip install a2a-lite[anthropic]"
                    )

                user_message = _extract_user_message(kwargs)
                client = anthropic.AsyncAnthropic(**extra_kwargs)

                async with client.messages.stream(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                ) as stream:
                    async for text in stream.text_stream:
                        yield text

            return streaming_wrapper
        else:

            @functools.wraps(func)
            async def wrapper(**kwargs: Any) -> str:
                try:
                    import anthropic
                except ImportError:
                    raise ImportError(
                        "Anthropic integration requires the 'anthropic' package. "
                        "Install it with: pip install a2a-lite[anthropic]"
                    )

                user_message = _extract_user_message(kwargs)
                client = anthropic.AsyncAnthropic(**extra_kwargs)
                response = await client.messages.create(
                    model=model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                # Extract text from content blocks
                text_parts = [
                    block.text for block in response.content if hasattr(block, "text")
                ]
                return "".join(text_parts)

            return wrapper

    return decorator


def ollama_skill(
    model: str = "llama3.2",
    base_url: str = "http://localhost:11434",
    system_prompt: str = "You are a helpful assistant.",
    temperature: float = 0.7,
    streaming: bool = False,
) -> Callable:
    """Decorator that wraps a skill to call a local Ollama instance.

    Uses httpx (already a core dep) to call the Ollama HTTP API directly,
    so no additional packages are required.

    Args:
        model: Ollama model name.
        base_url: Ollama server URL.
        system_prompt: System message.
        temperature: Sampling temperature.
        streaming: Whether to stream tokens.

    Returns:
        A decorator that replaces the skill handler.

    Example:
        @agent.skill("local_chat")
        @ollama_skill(model="llama3.2")
        async def local_chat(message: str) -> str:
            ...
    """

    def decorator(func: Callable) -> Callable:
        if streaming:

            @functools.wraps(func)
            async def streaming_wrapper(**kwargs: Any):  # type: ignore[misc]
                import httpx

                user_message = _extract_user_message(kwargs)
                url = f"{base_url.rstrip('/')}/api/chat"
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": True,
                    "options": {"temperature": temperature},
                }

                async with httpx.AsyncClient() as client:
                    async with client.stream(
                        "POST", url, json=payload, timeout=120.0
                    ) as response:
                        import json as _json

                        async for line in response.aiter_lines():
                            if line.strip():
                                data = _json.loads(line)
                                content = data.get("message", {}).get("content", "")
                                if content:
                                    yield content

            return streaming_wrapper
        else:

            @functools.wraps(func)
            async def wrapper(**kwargs: Any) -> str:
                import httpx

                user_message = _extract_user_message(kwargs)
                url = f"{base_url.rstrip('/')}/api/chat"
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    "options": {"temperature": temperature},
                }

                async with httpx.AsyncClient() as client:
                    response = await client.post(url, json=payload, timeout=120.0)
                    response.raise_for_status()
                    data = response.json()
                    return data.get("message", {}).get("content", "")

            return wrapper

    return decorator


def _extract_user_message(kwargs: dict[str, Any]) -> str:
    """Extract the user message from skill kwargs.

    Looks for common parameter names: message, text, query, prompt, input.
    Falls back to the first string value.

    Args:
        kwargs: The keyword arguments passed to the skill.

    Returns:
        The user message string.
    """
    for key in ("message", "text", "query", "prompt", "input"):
        if key in kwargs:
            return str(kwargs[key])
    # Fallback: use the first string value
    for value in kwargs.values():
        if isinstance(value, str):
            return value
    return str(next(iter(kwargs.values()), ""))
