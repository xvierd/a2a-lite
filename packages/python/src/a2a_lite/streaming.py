"""
Streaming support for A2A Lite agents.

Enables generator-based streaming for LLM-style responses:

    @agent.skill("chat", streaming=True)
    async def chat(message: str):
        async for chunk in llm.stream(message):
            yield chunk
"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Callable, Generator, Union
import inspect


def is_generator_function(func: Callable) -> bool:
    """Check if a function is a generator (sync or async)."""
    return inspect.isgeneratorfunction(func) or inspect.isasyncgenfunction(func)


async def collect_generator(gen: Union[Generator, AsyncGenerator]) -> list[Any]:
    """Collect all items from a generator into a list."""
    items = []
    if inspect.isasyncgen(gen):
        async for item in gen:
            items.append(item)
    else:
        for item in gen:
            items.append(item)
    return items


async def stream_generator(
    gen: Union[Generator, AsyncGenerator],
    event_queue,
) -> None:
    """
    Stream generator output through the A2A event queue.

    Each yielded item becomes a separate event in the stream.
    """
    from a2a.utils import new_agent_text_message

    if inspect.isasyncgen(gen):
        async for chunk in gen:
            text = str(chunk) if not isinstance(chunk, str) else chunk
            await event_queue.enqueue_event(new_agent_text_message(text))
    else:
        for chunk in gen:
            text = str(chunk) if not isinstance(chunk, str) else chunk
            await event_queue.enqueue_event(new_agent_text_message(text))
