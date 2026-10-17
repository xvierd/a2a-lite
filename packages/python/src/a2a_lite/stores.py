"""Protocol store limits applied equally to default and external SDK stores."""

import asyncio
import time

from a2a.server.cluster.task_store import LegacyTaskStoreAdapter, VersionedTaskStore
from a2a.server.context import ServerCallContext
from a2a.server.tasks import InMemoryTaskStore, TaskStore
from a2a.types import TaskState


class BoundedTaskStore(VersionedTaskStore):
    def __init__(self, store, config):
        self.store = store if isinstance(store, VersionedTaskStore) else LegacyTaskStoreAdapter(store)
        self.config = config

    def __getattr__(self, name):
        return getattr(self.store, name)

    async def save(self, task, *, event, prev, prev_version, context):
        # Retain the newest history/artifacts. These are snapshots; the durable
        # event log has its own explicit operator retention policy.
        excess = len(task.history) - self.config.max_history_messages
        if excess > 0:
            del task.history[:excess]
        excess = len(task.artifacts) - self.config.max_artifacts
        if excess > 0:
            del task.artifacts[:excess]
        return await self.store.save(task, event=event, prev=prev, prev_version=prev_version, context=context)

    async def get(self, task_id, context):
        return await self.store.get(task_id, context)

    async def list(self, params, context):
        return await self.store.list(params, context)

    async def delete(self, task_id, context):
        return await self.store.delete(task_id, context)


class BoundedLegacyTaskStore(TaskStore):
    def __init__(self, store, config):
        self.store, self.config = store, config
        self.memory = isinstance(store, InMemoryTaskStore)
        self.entries = {}
        self.lock = asyncio.Lock()

    async def _expire(self):
        now = time.monotonic()
        for task_id, (updated, terminal, context) in list(self.entries.items()):
            if terminal and now - updated > self.config.task_ttl:
                await self.store.delete(task_id, context=context)
                del self.entries[task_id]

    async def save(self, task, context=None):
        excess = len(task.history) - self.config.max_history_messages
        if excess > 0:
            del task.history[:excess]
        excess = len(task.artifacts) - self.config.max_artifacts
        if excess > 0:
            del task.artifacts[:excess]
        if not self.memory:
            return await self.store.save(task, context=context)
        async with self.lock:
            await self._expire()
            if task.id not in self.entries and len(self.entries) >= self.config.max_stored_tasks:
                terminal = [(value[0], key, value[2]) for key, value in self.entries.items() if value[1]]
                if not terminal:
                    raise RuntimeError("Stored task capacity exhausted")
                _, oldest, owner = min(terminal)
                await self.store.delete(oldest, context=owner)
                del self.entries[oldest]
            result = await self.store.save(task, context=context)
            owner = ServerCallContext(user=context.user, tenant=context.tenant) if context else ServerCallContext()
            terminal = task.status.state in (
                TaskState.TASK_STATE_COMPLETED,
                TaskState.TASK_STATE_FAILED,
                TaskState.TASK_STATE_CANCELED,
                TaskState.TASK_STATE_REJECTED,
            )
            self.entries[task.id] = (time.monotonic(), terminal, owner)
            return result

    async def get(self, task_id, context=None):
        if self.memory:
            async with self.lock:
                await self._expire()
        return await self.store.get(task_id, context=context)

    async def list(self, params, context=None):
        if self.memory:
            async with self.lock:
                await self._expire()
        return await self.store.list(params, context=context)

    async def delete(self, task_id, context=None):
        result = await self.store.delete(task_id, context=context)
        self.entries.pop(task_id, None)
        return result


def bound_task_store(store, config):
    wrapper = BoundedTaskStore if isinstance(store, VersionedTaskStore) else BoundedLegacyTaskStore
    return wrapper(store, config)
