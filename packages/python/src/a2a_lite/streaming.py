"""
Streaming support for A2A Lite agents.

Enables generator-based streaming for LLM-style responses:

    @agent.skill("chat", streaming=True)
    async def chat(message: str):
        async for chunk in llm.stream(message):
            yield chunk
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, Callable, Generator
from typing import Any, Union


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
    context=None,
    updater=None,
) -> None:
    """
    Stream generator output through the A2A event queue.

    When a TaskUpdater is provided (production path), the A2A 1.x strict
    event rules apply: status updates via TaskUpdater and task completion
    at the end. When only a RequestContext is provided, the Task and
    updater are created here (first event is the Task).

    Without either (direct unit testing), each chunk is enqueued as a
    single text message (legacy simple behavior).
    """
    if updater is None and context is not None:
        from a2a.helpers import new_task_from_user_message
        from a2a.server.tasks import TaskUpdater

        task = context.current_task or new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

    if updater is not None:
        from a2a.helpers import new_text_part
        from a2a.types import TaskState

        async def emit(text: str) -> None:
            await updater.update_status(
                TaskState.TASK_STATE_WORKING,
                message=updater.new_agent_message([new_text_part(text)]),
            )

    else:
        from a2a.helpers import new_text_message

        async def emit(text: str) -> None:
            await event_queue.enqueue_event(new_text_message(text))

    if inspect.isasyncgen(gen):
        async for chunk in gen:
            text = str(chunk) if not isinstance(chunk, str) else chunk
            await emit(text)
    else:
        for chunk in gen:
            text = str(chunk) if not isinstance(chunk, str) else chunk
            await emit(text)

    if updater is not None:
        await updater.complete()
