"""Run Message → Task → stream → authenticated peers → optional SQL restart.

    python main.py
    python main.py --durable-directory /tmp/a2a-learning-state

The second command installs no server: it uses SQLite and a persisted local key.
For PostgreSQL deployments use the package's production guide and external keys.
"""

import argparse
import asyncio
from pathlib import Path

from a2a_lite import Agent, AgentNetwork, ClientConfig, PersistenceConfig, RuntimeConfig, TaskContext
from a2a_lite.auth import APIKeyAuth


def create_agent(persistence=None):
    agent = Agent(
        "LearningPath", "Progress from local messages to durable task state",
        auth=APIKeyAuth(principals={"learning-key": "learner", "rotated-key": "learner"}),
        runtime=RuntimeConfig(profile="durable" if persistence else "authenticated"),
        persistence=persistence,
    )

    @agent.skill("greet")
    async def greet(name: str):
        return f"Hello, {name}!"

    @agent.skill("tracked", task=True)
    async def tracked(task: TaskContext):
        await task.update("working", "The ID below is the A2A protocol task ID")
        return task.task_id

    @agent.skill("words", streaming=True)
    async def words():
        for word in ("learn", "test", "operate"):
            yield word

    if persistence:
        @agent.skill("checkpointed", recoverable=True)
        async def checkpointed(task: TaskContext):
            # A restarted handler begins here again. Only committed work belongs
            # in the checkpoint; external effects require their own idempotency.
            previous = task.checkpoint_data or {"processed": 0}
            for index in range(previous["processed"], 3):
                await asyncio.sleep(0.01)
                await task.checkpoint({"processed": index + 1})
            return {"processed": 3, "taskId": task.task_id}

    return agent


async def main(directory=None):
    persistence = None
    if directory:
        from cryptography.fernet import Fernet
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        key_file = directory / "local-demo.key"
        if not key_file.exists():
            key_file.write_bytes(Fernet.generate_key())
            key_file.chmod(0o600)
        persistence = PersistenceConfig("sqlite+aiosqlite:///"+str(directory/"state.db"), key_file.read_bytes())
        await persistence.migrate()
    runtime = await create_agent(persistence).start()
    network = AgentNetwork()
    network.add("peer", runtime.url, client_config=ClientConfig(headers={"X-API-Key": "learning-key"}))
    try:
        print("Message:", await network.call("peer", "greet", name="A2A"))
        handle = await network.call("peer", "tracked", return_handle=True)
        assert handle.result == handle.task_id
        print("Task:", handle.task_id, (await handle.get_status())["status"]["state"])
        print("Stream:", [part async for part in network.stream("peer", "words")])
        if persistence:
            checkpointed = await network.call("peer", "checkpointed", return_handle=True)
            print("Checkpoint result:", checkpointed.result)
        print("Runtime:", runtime.stats)
    finally:
        await runtime.stop()
    if persistence:
        restarted = await create_agent(persistence).start()
        try:
            # Rotating the API key keeps the stable principal and task ownership.
            network.add("peer", restarted.url, client_config=ClientConfig(headers={"X-API-Key": "rotated-key"}))
            restored = await network.get_task("peer", handle.task_id)
            assert restored["id"] == handle.task_id
            print("After restart and key rotation:", restored["id"])
        finally:
            await restarted.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--durable-directory")
    asyncio.run(main(parser.parse_args().durable_directory))
