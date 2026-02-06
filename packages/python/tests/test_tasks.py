"""
Tests for task lifecycle management.
"""
import pytest
from a2a_lite.tasks import (
    TaskState,
    TaskStatus,
    Task,
    TaskContext,
    TaskStore,
)


class TestTaskState:
    def test_states_exist(self):
        assert TaskState.SUBMITTED.value == "submitted"
        assert TaskState.WORKING.value == "working"
        assert TaskState.INPUT_REQUIRED.value == "input-required"
        assert TaskState.COMPLETED.value == "completed"
        assert TaskState.FAILED.value == "failed"
        assert TaskState.CANCELED.value == "canceled"


class TestTaskStatus:
    def test_creation(self):
        status = TaskStatus(
            state=TaskState.WORKING,
            message="Processing...",
            progress=0.5,
        )
        assert status.state == TaskState.WORKING
        assert status.message == "Processing..."
        assert status.progress == 0.5

    def test_to_dict(self):
        status = TaskStatus(state=TaskState.WORKING, progress=0.5)
        result = status.to_dict()

        assert result["state"] == "working"
        assert result["progress"] == 0.5
        assert "timestamp" in result


class TestTask:
    def test_creation(self):
        task = Task(
            id="task-123",
            skill="process",
            params={"data": "test"},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        assert task.id == "task-123"
        assert task.skill == "process"

    def test_update_status(self):
        task = Task(
            id="task-123",
            skill="process",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )

        task.update_status(TaskState.WORKING, "Starting...", 0.0)

        assert task.status.state == TaskState.WORKING
        assert task.status.message == "Starting..."
        assert len(task.history) == 1  # Previous status in history


class TestTaskStore:
    @pytest.mark.asyncio
    async def test_create(self):
        store = TaskStore()
        task = await store.create("process", {"data": "test"})

        assert task.id is not None
        assert task.skill == "process"
        assert task.status.state == TaskState.SUBMITTED

    @pytest.mark.asyncio
    async def test_get(self):
        store = TaskStore()
        task = await store.create("process", {})

        retrieved = await store.get(task.id)
        assert retrieved is not None
        assert retrieved.id == task.id

    @pytest.mark.asyncio
    async def test_get_nonexistent(self):
        store = TaskStore()
        assert await store.get("nonexistent") is None

    @pytest.mark.asyncio
    async def test_list(self):
        store = TaskStore()
        await store.create("skill1", {})
        await store.create("skill2", {})
        await store.create("skill1", {})

        all_tasks = await store.list()
        assert len(all_tasks) == 3

    @pytest.mark.asyncio
    async def test_list_by_skill(self):
        store = TaskStore()
        await store.create("skill1", {})
        await store.create("skill2", {})
        await store.create("skill1", {})

        skill1_tasks = await store.list(skill="skill1")
        assert len(skill1_tasks) == 2

    @pytest.mark.asyncio
    async def test_list_by_state(self):
        store = TaskStore()
        task1 = await store.create("skill", {})
        task2 = await store.create("skill", {})

        task1.update_status(TaskState.COMPLETED)
        await store.update(task1)

        completed = await store.list(state=TaskState.COMPLETED)
        assert len(completed) == 1

    @pytest.mark.asyncio
    async def test_delete(self):
        store = TaskStore()
        task = await store.create("process", {})

        assert await store.delete(task.id) is True
        assert await store.get(task.id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self):
        store = TaskStore()
        assert await store.delete("nonexistent") is False


class TestTaskContext:
    def test_creation(self):
        task = Task(
            id="task-123",
            skill="process",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        ctx = TaskContext(task)

        assert ctx.task_id == "task-123"
        assert ctx.state == TaskState.SUBMITTED

    @pytest.mark.asyncio
    async def test_update(self):
        task = Task(
            id="task-123",
            skill="process",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        ctx = TaskContext(task)

        await ctx.update("working", "Processing...", 0.5)

        assert task.status.state == TaskState.WORKING
        assert task.status.message == "Processing..."
        assert task.status.progress == 0.5

    @pytest.mark.asyncio
    async def test_status_callback(self):
        task = Task(
            id="task-123",
            skill="process",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        ctx = TaskContext(task)

        callbacks_received = []

        def callback(status):
            callbacks_received.append(status)

        ctx.on_status_change(callback)
        await ctx.update("working", "Step 1")
        await ctx.update("working", "Step 2")

        assert len(callbacks_received) == 2
