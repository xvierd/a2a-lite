"""
Example: Task lifecycle and progress tracking.

Show users real-time progress for long-running tasks.

Run: python examples/11_task_tracking.py
"""
import asyncio
from a2a_lite import Agent, TaskContext

# Enable task store for tracking
agent = Agent(
    name="TaskTracker",
    description="Shows task progress",
    task_store="memory",  # Enable task tracking
)


@agent.skill("long_process")
async def long_process(steps: int, task: TaskContext) -> dict:
    """
    Long-running task with progress updates.
    TaskContext is auto-injected when you add it as a parameter.
    """
    await task.update("working", "Starting process...", progress=0.0)

    for i in range(steps):
        # Do some work
        await asyncio.sleep(0.5)

        # Update progress
        progress = (i + 1) / steps
        await task.update(
            "working",
            f"Processing step {i + 1}/{steps}",
            progress=progress
        )

    return {
        "status": "completed",
        "steps_completed": steps,
        "task_id": task.task_id,
    }


@agent.skill("batch_import")
async def batch_import(items: list, task: TaskContext) -> dict:
    """Import items with progress tracking."""
    total = len(items)
    successful = 0
    failed = 0

    await task.update("working", f"Importing {total} items...", progress=0.0)

    for i, item in enumerate(items):
        try:
            # Simulate import
            await asyncio.sleep(0.1)
            successful += 1
        except Exception:
            failed += 1

        # Update progress
        await task.update(
            "working",
            f"Imported {i + 1}/{total} ({failed} failed)",
            progress=(i + 1) / total
        )

    return {
        "total": total,
        "successful": successful,
        "failed": failed,
    }


if __name__ == "__main__":
    agent.run(port=8787)
