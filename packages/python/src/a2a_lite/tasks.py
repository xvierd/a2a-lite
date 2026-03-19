"""
Task lifecycle management (OPTIONAL).

By default, A2A Lite just returns results (simple mode).
Enable task tracking when you need:
- Progress updates
- Long-running tasks
- Task status visibility

Example (simple - no task tracking needed):
    @agent.skill("greet")
    async def greet(name: str) -> str:
        return f"Hello, {name}!"

Example (with task tracking - opt-in):
    agent = Agent(name="Bot", task_store="memory")  # Enable tracking

    @agent.skill("process")
    async def process(data: str, task: TaskContext) -> str:
        await task.update("working", "Starting...", progress=0.0)

        for i in range(10):
            await task.update("working", f"Step {i+1}/10", progress=i/10)
            await do_work(i)

        return "Done!"
"""

from __future__ import annotations

import asyncio
import builtins
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class TaskState(str, Enum):
    """A2A Protocol task states."""

    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    AUTH_REQUIRED = "auth-required"


@dataclass
class TaskStatus:
    """Current status of a task."""

    state: TaskState
    message: str | None = None
    progress: float | None = None  # 0.0 to 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "message": self.message,
            "progress": self.progress,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Task:
    """Represents an A2A task."""

    id: str
    skill: str
    params: dict[str, Any]
    status: TaskStatus
    result: Any = None
    error: str | None = None
    artifacts: list[Any] = field(default_factory=list)
    history: list[TaskStatus] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def update_status(
        self,
        state: TaskState,
        message: str | None = None,
        progress: float | None = None,
    ) -> None:
        """Update task status."""
        self.history.append(self.status)
        self.status = TaskStatus(state=state, message=message, progress=progress)
        self.updated_at = datetime.now(timezone.utc)


class TaskContext:
    """
    Context passed to skills when task tracking is enabled.

    Provides methods to update task status and request user input.

    Example:
        @agent.skill("process")
        async def process(data: str, task: TaskContext) -> str:
            await task.update("working", "Processing...", progress=0.5)
            result = await heavy_computation(data)
            return result
    """

    def __init__(self, task: Task, event_queue=None, input_handler=None):
        self._task = task
        self._event_queue = event_queue
        self._input_handler = input_handler
        self._status_callbacks: list[Callable] = []

    @property
    def task_id(self) -> str:
        return self._task.id

    @property
    def state(self) -> TaskState:
        return self._task.status.state

    async def update(
        self,
        state: str = "working",
        message: str | None = None,
        progress: float | None = None,
    ) -> None:
        """
        Update task status.

        Args:
            state: Task state (working, completed, failed, etc.)
            message: Human-readable status message
            progress: Progress from 0.0 to 1.0

        Example:
            await task.update("working", "Processing item 5/10", progress=0.5)
        """
        task_state = TaskState(state) if isinstance(state, str) else state
        self._task.update_status(task_state, message, progress)

        # Notify callbacks
        for callback in self._status_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(self._task.status)
                else:
                    callback(self._task.status)
            except Exception:
                logger.warning("Status callback error for task '%s'", self._task.id, exc_info=True)

        # Send SSE event if streaming
        if self._event_queue:
            await self._send_status_event()

    async def _send_status_event(self) -> None:
        """Send status update via SSE."""
        if self._event_queue:
            import json

            from a2a.utils import new_agent_text_message

            status_msg = json.dumps(
                {
                    "_type": "status_update",
                    "task_id": self._task.id,
                    "status": self._task.status.to_dict(),
                }
            )
            await self._event_queue.enqueue_event(new_agent_text_message(status_msg))

    def on_status_change(self, callback: Callable) -> None:
        """Register callback for status changes."""
        self._status_callbacks.append(callback)


class TaskStore:
    """
    In-memory task store with async locking for thread safety.

    For production, extend this with Redis/DB backend.
    """

    def __init__(self, max_size: int = 10000, ttl_seconds: float = 3600):
        self._tasks: dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds

    def _evict(self) -> None:
        """Remove expired tasks and enforce max_size (oldest first)."""
        now = datetime.now(timezone.utc)

        # Remove tasks older than TTL
        expired = [tid for tid, t in self._tasks.items() if (now - t.created_at).total_seconds() > self._ttl_seconds]
        for tid in expired:
            del self._tasks[tid]

        # Evict oldest if still over max_size
        if len(self._tasks) >= self._max_size:
            sorted_tasks = sorted(self._tasks.items(), key=lambda item: item[1].created_at)
            excess = len(self._tasks) - self._max_size + 1
            for tid, _ in sorted_tasks[:excess]:
                del self._tasks[tid]

    async def create(self, skill: str, params: dict[str, Any]) -> Task:
        """Create a new task."""
        async with self._lock:
            self._evict()
            task = Task(
                id=uuid4().hex,
                skill=skill,
                params=params,
                status=TaskStatus(state=TaskState.SUBMITTED),
            )
            self._tasks[task.id] = task
            return task

    async def get(self, task_id: str) -> Task | None:
        """Get task by ID."""
        async with self._lock:
            return self._tasks.get(task_id)

    async def update(self, task: Task) -> None:
        """Update task in store."""
        async with self._lock:
            self._tasks[task.id] = task

    async def list(
        self,
        state: TaskState | None = None,
        skill: str | None = None,
        limit: int = 100,
    ) -> builtins.list[Task]:
        """List tasks with optional filters."""
        async with self._lock:
            tasks = list(self._tasks.values())

            if state:
                tasks = [t for t in tasks if t.status.state == state]
            if skill:
                tasks = [t for t in tasks if t.skill == skill]

            return sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]

    async def delete(self, task_id: str) -> bool:
        """Delete a task."""
        async with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False
