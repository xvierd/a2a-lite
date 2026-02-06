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

    @pytest.mark.asyncio
    async def test_update_with_task_state_enum(self):
        """Test updating with TaskState enum directly."""
        task = Task(
            id="task-123",
            skill="process",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        ctx = TaskContext(task)
        await ctx.update(TaskState.COMPLETED, "Done!")
        assert task.status.state == TaskState.COMPLETED

    @pytest.mark.asyncio
    async def test_multiple_status_changes_tracked_in_history(self):
        """Test that multiple updates create history entries."""
        task = Task(
            id="task-123",
            skill="process",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        ctx = TaskContext(task)

        await ctx.update("working", "Step 1", 0.25)
        await ctx.update("working", "Step 2", 0.50)
        await ctx.update("working", "Step 3", 0.75)
        await ctx.update("completed", "Done!", 1.0)

        assert task.status.state == TaskState.COMPLETED
        assert len(task.history) == 4  # SUBMITTED + 3 WORKING

    @pytest.mark.asyncio
    async def test_async_status_callback(self):
        """Test that async status callbacks are awaited."""
        task = Task(
            id="task-123",
            skill="process",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        ctx = TaskContext(task)

        callbacks_received = []

        async def async_callback(status):
            callbacks_received.append(status.state)

        ctx.on_status_change(async_callback)
        await ctx.update("working", "Step 1")

        assert len(callbacks_received) == 1
        assert callbacks_received[0] == TaskState.WORKING

    @pytest.mark.asyncio
    async def test_send_status_event_with_event_queue(self):
        """Test that status updates are sent via event queue when provided."""
        events = []

        class MockEventQueue:
            async def enqueue_event(self, event):
                events.append(event)

        task = Task(
            id="task-123",
            skill="process",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        ctx = TaskContext(task, event_queue=MockEventQueue())
        await ctx.update("working", "Processing...")

        assert len(events) == 1


class TestTaskStoreEdgeCases:
    @pytest.mark.asyncio
    async def test_list_with_limit(self):
        """Test that list respects the limit parameter."""
        store = TaskStore()
        for i in range(10):
            await store.create("skill", {"i": i})

        tasks = await store.list(limit=5)
        assert len(tasks) == 5

    @pytest.mark.asyncio
    async def test_update(self):
        """Test updating a task in the store."""
        store = TaskStore()
        task = await store.create("skill", {})
        task.update_status(TaskState.WORKING, "Processing")
        await store.update(task)

        retrieved = await store.get(task.id)
        assert retrieved.status.state == TaskState.WORKING

    @pytest.mark.asyncio
    async def test_list_returns_sorted_by_created_at(self):
        """Test that list returns tasks sorted by creation time (newest first)."""
        import asyncio
        store = TaskStore()
        t1 = await store.create("skill", {"order": 1})
        await asyncio.sleep(0.01)
        t2 = await store.create("skill", {"order": 2})

        tasks = await store.list()
        assert tasks[0].id == t2.id  # Newest first


class TestTaskStateValues:
    def test_auth_required_state(self):
        """Test AUTH_REQUIRED state exists."""
        assert TaskState.AUTH_REQUIRED.value == "auth-required"

    def test_all_states(self):
        """Test all states are accessible."""
        states = list(TaskState)
        assert len(states) == 7  # 7 states total


class TestTaskStatusDefaults:
    def test_default_message(self):
        """Test that message defaults to None."""
        status = TaskStatus(state=TaskState.SUBMITTED)
        assert status.message is None

    def test_default_progress(self):
        """Test that progress defaults to None."""
        status = TaskStatus(state=TaskState.SUBMITTED)
        assert status.progress is None

    def test_timestamp_auto_set(self):
        """Test that timestamp is automatically set."""
        status = TaskStatus(state=TaskState.SUBMITTED)
        assert status.timestamp is not None


class TestTaskDefaults:
    def test_default_fields(self):
        """Test Task default field values."""
        task = Task(
            id="test",
            skill="skill",
            params={},
            status=TaskStatus(state=TaskState.SUBMITTED),
        )
        assert task.result is None
        assert task.error is None
        assert task.artifacts == []
        assert task.history == []
        assert task.created_at is not None
        assert task.updated_at is not None
