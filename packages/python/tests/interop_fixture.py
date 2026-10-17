"""Live cross-language fixture. No external LLMs or callback requests."""

import argparse
import asyncio
import base64
import json
import os

from a2a_lite import Agent, AgentNetwork, ClientConfig, PersistenceConfig, RuntimeConfig, TaskContext
from a2a_lite.auth import APIKeyAuth


def create_agent():
    dsn = os.getenv("A2ALITE_INTEROP_POSTGRES_DSN")
    persistence = (
        PersistenceConfig(dsn, base64.urlsafe_b64encode(bytes([7]) * 32), dispatch_callbacks=False) if dsn else None
    )
    agent = Agent(
        name="PythonInterop",
        description="Live A2A protocol fixture",
        runtime=RuntimeConfig(profile="durable" if persistence else "authenticated"),
        persistence=persistence,
        auth=APIKeyAuth(principals={"interop-secret": "alice", "interop-rotated": "alice", "interop-other": "bob"}),
    )

    @agent.skill("greet")
    async def greet(text: str):
        return text

    @agent.skill("taskProbe", task=True)
    async def task_probe(task: TaskContext):
        return task.task_id

    @agent.skill("pause", task=True)
    async def pause(task: TaskContext, resume: bool = False):
        if not resume:
            await task.update("input-required", "Send resume=true to continue")
            return None
        return "resumed"

    @agent.skill("stream", streaming=True)
    async def stream():
        for part in ("one", "two", "three"):
            yield part

    @agent.skill("hold", streaming=True)
    async def hold():
        for index in range(100):
            await asyncio.sleep(0.05)
            yield str(index)

    @agent.skill("delay")
    async def delay():
        await asyncio.sleep(0.02)
        return "ok"

    @agent.skill("fail", task=True)
    async def fail():
        raise ValueError("Fixture failure")

    return agent


async def main(args):
    if args.mode == "server":
        agent = create_agent()
        if agent.persistence:
            await agent.persistence.migrate()
        runtime = await agent.start(port=args.port)
        print("A2A_LITE_READY " + json.dumps({"url": runtime.url}), flush=True)
        try:
            await runtime._task
        finally:
            await runtime.stop()
        return
    network = AgentNetwork()
    network.add("peer", args.url, client_config=ClientConfig(headers={"X-API-Key": "interop-secret"}))
    card = await network.discover("peer")
    assert any(i["protocolVersion"] == "1.0" for i in card.raw["supportedInterfaces"])
    message = await network.call("peer", "greet", text="hello")
    task = await network.call("peer", "taskProbe", return_handle=True)
    read = await task.get_status()
    chunks = [part async for part in network.stream("peer", "stream")]
    result = {
        "message": message == "hello",
        "task": task.result == task.task_id,
        "taskRead": read["id"] == task.task_id,
        "stream": chunks == ["one", "two", "three"],
    }
    print("A2A_LITE_RESULT " + json.dumps(result), flush=True)
    assert all(result.values()), result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("server").add_argument("--port", type=int, required=True)
    modes.add_parser("client").add_argument("--url", required=True)
    asyncio.run(main(parser.parse_args()))
