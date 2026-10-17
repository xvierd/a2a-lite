"""Bounded execution and resource ownership for local A2A runtimes."""

from __future__ import annotations

import asyncio
import inspect
import socket
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RuntimeConfig:
    """Profiles are guarantees, not deployment labels. Timeouts use seconds."""

    profile: Literal["learning", "authenticated", "durable"] = "learning"
    max_concurrent_tasks: int = 64
    max_per_principal: int = 16
    max_stored_tasks: int = 10000
    task_ttl: float = 3600.0
    max_request_bytes: int = 1024 * 1024
    max_streams: int = 128
    max_push_configs: int = 16
    max_history_messages: int = 100
    max_artifacts: int = 128
    max_event_bytes: int = 1024 * 1024
    max_output_bytes: int = 8 * 1024 * 1024
    execution_timeout: float = 300.0
    shutdown_timeout: float = 10.0

    def __post_init__(self):
        if self.profile not in ("learning", "authenticated", "durable"):
            raise ValueError("Unknown runtime profile")
        for name in (
            "max_concurrent_tasks",
            "max_per_principal",
            "max_stored_tasks",
            "max_request_bytes",
            "max_event_bytes",
            "max_output_bytes",
            "max_streams",
            "max_push_configs",
            "max_history_messages",
            "max_artifacts",
        ):
            if (
                not isinstance(getattr(self, name), int)
                or isinstance(getattr(self, name), bool)
                or getattr(self, name) <= 0
            ):
                raise ValueError(f"{name} must be a positive integer")
        for name in ("execution_timeout", "shutdown_timeout", "task_ttl"):
            import math

            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be positive and finite")


class OutputLimitError(Exception):
    """An event or the complete execution exceeded its configured output budget."""


class LimitedEventQueue:
    def __init__(self, queue, config):
        self.queue, self.config = queue, config
        self.size = 0
        self.task = None
        self.terminal = False
        self.failed = False

    def __getattr__(self, name):
        return getattr(self.queue, name)

    async def enqueue_event(self, event):
        from a2a.types import Task, TaskState, TaskStatusUpdateEvent

        size = event.ByteSize()
        if size > self.config.max_event_bytes or self.size + size > self.config.max_output_bytes:
            raise OutputLimitError("Output limit exceeded")
        self.size += size
        if isinstance(event, Task):
            self.task = event
        if isinstance(event, TaskStatusUpdateEvent):
            self.failed = event.status.state == TaskState.TASK_STATE_FAILED
            self.terminal = event.status.state in (
                TaskState.TASK_STATE_COMPLETED,
                TaskState.TASK_STATE_FAILED,
                TaskState.TASK_STATE_CANCELED,
                TaskState.TASK_STATE_REJECTED,
            )
        await self.queue.enqueue_event(event)

    async def fail(self, context, reason, *, rejected=False):
        from a2a.helpers import new_task_from_user_message, new_text_part
        from a2a.server.tasks import TaskUpdater
        from a2a.types import TaskState

        if self.terminal:
            return
        if self.task is None:
            self.task = new_task_from_user_message(context.message)
            self.task.id, self.task.context_id = context.task_id, context.context_id
            await self.queue.enqueue_event(self.task)
        updater = TaskUpdater(self.queue, self.task.id, self.task.context_id)
        message = updater.new_agent_message([new_text_part(reason)])
        state = TaskState.TASK_STATE_REJECTED if rejected else TaskState.TASK_STATE_FAILED
        await updater.update_status(state, message=message)
        self.terminal = True


class RuntimeState:
    def __init__(self, config):
        self.config = config
        self.ready = False
        self.accepting = True
        self.active = set()
        self.streams = 0
        self.principals = {}
        self.uncooperative = 0
        self.counters = {"accepted": 0, "rejected": 0, "completed": 0, "failed": 0, "timed_out": 0, "canceled": 0}

    def snapshot(self):
        return {
            "profile": self.config.profile,
            "ready": self.ready,
            "accepting": self.accepting,
            "active": len(self.active),
            "streams": self.streams,
            "uncooperative": self.uncooperative,
            **self.counters,
        }

    async def execute(self, execute, context, queue):
        bounded = LimitedEventQueue(queue, self.config)
        principal = context.call_context.user.user_name if context.call_context else "anonymous"
        if (
            not self.accepting
            or len(self.active) >= self.config.max_concurrent_tasks
            or self.principals.get(principal, 0) >= self.config.max_per_principal
        ):
            self.counters["rejected"] += 1
            await bounded.fail(context, "Runtime capacity exhausted", rejected=True)
            return
        current = asyncio.current_task()
        self.active.add(current)
        self.principals[principal] = self.principals.get(principal, 0) + 1
        self.counters["accepted"] += 1
        try:
            await asyncio.wait_for(execute(context, bounded), self.config.execution_timeout)
            self.counters["failed" if bounded.failed else "completed"] += 1
        except asyncio.TimeoutError:
            self.counters["timed_out"] += 1
            await bounded.fail(context, "Execution deadline exceeded")
        except OutputLimitError:
            self.counters["failed"] += 1
            await bounded.fail(context, "Output limit exceeded")
        except asyncio.CancelledError:
            self.counters["canceled"] += 1
            await bounded.fail(context, "Execution interrupted by shutdown")
            raise
        finally:
            self.active.discard(current)
            self.principals[principal] -= 1
            if not self.principals[principal]:
                del self.principals[principal]

    async def drain(self):
        self.accepting = self.ready = False
        if self.active:
            _, pending = await asyncio.wait(tuple(self.active), timeout=self.config.shutdown_timeout)
            for task in pending:
                task.cancel()
            if pending:
                _, still_running = await asyncio.wait(pending, timeout=self.config.shutdown_timeout)
                self.uncooperative = len(still_running)


async def run_hooks(hooks):
    for hook in hooks:
        result = hook()
        if inspect.isawaitable(result):
            await result


class RuntimeLifecycle:
    def __init__(self, agent, handler, state, backend=None):
        self.agent, self.handler, self.state, self.backend = agent, handler, state, backend
        self.started = self.closed = False

    async def start(self):
        if self.closed:
            raise RuntimeError("Runtime is closed; build a new runtime to restart")
        if self.started:
            return
        try:
            if self.backend:
                await self.backend.start()
            await run_hooks(self.agent._on_startup)
            self.state.ready = True
            self.started = True
        except BaseException:
            await self.stop()
            raise

    async def stop(self):
        if self.closed:
            return
        self.closed = True

        async def bounded_close(operation):
            closing = asyncio.create_task(operation)
            _, pending = await asyncio.wait({closing}, timeout=self.state.config.shutdown_timeout)
            if pending:
                self.state.uncooperative = max(self.state.uncooperative, 1)
                closing.cancel()
                closing.add_done_callback(lambda done: None if done.cancelled() else done.exception())
                return None
            return closing.result()

        try:
            await self.state.drain()
            await bounded_close(self.handler.aclose())
        finally:
            try:
                await bounded_close(run_hooks(self.agent._on_shutdown))
            finally:
                if self.backend:
                    # Leave room for pool/client disposal after bounded lease
                    # revocation, runner cancellation and callback cancellation.
                    count = await bounded_close(self.backend.close(timeout=self.state.config.shutdown_timeout / 4))
                    self.state.uncooperative = max(self.state.uncooperative, count or 0)


class ManagedRuntime:
    """An HTTP server with explicit readiness, stats, and idempotent shutdown."""

    def __init__(self, server, task, app, url):
        self._server, self._task, self._app, self.url = server, task, app, url

    @property
    def storage(self):
        """Trusted operator interface for callback replay, key rotation and retention."""
        return self._app.state.runtime.backend

    @property
    def ready(self):
        return self._app.state.runtime.state.ready and not self._task.done()

    @property
    def stats(self):
        return self._app.state.runtime.state.snapshot()

    async def stop(self):
        self._app.state.runtime.state.accepting = False
        self._server.should_exit = True
        await self._task

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        await self.stop()


async def start_http(agent, host, port, log_level):
    import uvicorn

    sock = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        sock.listen(128)
        actual_port = sock.getsockname()[1]
        display_host = "localhost" if host in ("0.0.0.0", "::") else host
        app = agent._build_app(display_host, actual_port)

        class EmbeddedServer(uvicorn.Server):
            @contextmanager
            def capture_signals(self):
                yield

        server = EmbeddedServer(
            uvicorn.Config(app, log_level=log_level, timeout_graceful_shutdown=agent._runtime_config.shutdown_timeout)
        )
        task = asyncio.create_task(server.serve(sockets=[sock]))
        while not server.started:
            if task.done():
                await task
                raise RuntimeError("HTTP runtime did not start")
            await asyncio.sleep(0.01)
        return ManagedRuntime(server, task, app, f"http://{display_host}:{actual_port}")
    except BaseException:
        sock.close()
        raise
