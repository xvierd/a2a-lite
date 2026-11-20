"""Run with the interpreter from the clean registry installation."""

import asyncio
import sys
from importlib.metadata import version
from pathlib import Path

import a2a_lite
from a2a_lite import Agent, AgentNetwork, TaskContext


async def main():
    assert version("a2a-lite") == a2a_lite.__version__ == sys.argv[1]
    assert Path(a2a_lite.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
    agent = Agent(name="Release", description="Published package smoke")

    @agent.skill("echo", tags=["release"])
    async def echo(text: str):
        return text

    @agent.skill("tracked", task=True, tags=["release"])
    async def tracked(task: TaskContext):
        return task.task_id

    @agent.skill("stream", streaming=True, tags=["release"])
    async def stream():
        for text in ("first", "second"):
            yield text

    runtime = await agent.start(host="127.0.0.1", port=0)
    try:
        peer = AgentNetwork({"local": runtime.url})
        await peer.discover("local")
        assert await peer.call("local", "echo", text="hello") == "hello"
        handle = await peer.call("local", "tracked", return_handle=True)
        assert handle.task_id and handle.result == handle.task_id
        task = await handle.get_status()
        assert task["id"] == handle.task_id and task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert [part async for part in peer.stream("local", "stream")] == ["first", "second"]
    finally:
        await runtime.stop()


if __name__ == "__main__":
    asyncio.run(main())
