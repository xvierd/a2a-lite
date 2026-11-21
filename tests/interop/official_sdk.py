"""Exercise the public Python ClientFactory on one advertised binding."""

import argparse
import asyncio
import json
from importlib.metadata import version
from uuid import uuid4

import httpx
from a2a.client import ClientConfig, ClientFactory
from a2a.types.a2a_pb2 import (
    ROLE_AGENT,
    ROLE_USER,
    TASK_STATE_COMPLETED,
    TASK_STATE_FAILED,
    TASK_STATE_SUBMITTED,
    TASK_STATE_WORKING,
    GetTaskRequest,
    Message,
    Part,
    SendMessageRequest,
)
from a2a.utils.errors import TaskNotFoundError


def message(skill, **params):
    return SendMessageRequest(
        message=Message(
            message_id=uuid4().hex,
            role=ROLE_USER,
            parts=[Part(text=json.dumps({"skill": skill, "params": params}))],
        ),
    )


def texts(parts):
    return [part.text for part in parts if part.HasField("text")]


async def check_stream(client, skill, terminal):
    task_id = None
    chunks = []
    ended = False
    async for event in client.send_message(message(skill)):
        assert not ended, f"{skill}: event after terminal status"
        if task_id is None:
            assert event.HasField("task") and event.task.id, (
                f"{skill}: missing initial Task"
            )
            task_id = event.task.id
            continue
        if event.HasField("artifact_update"):
            update = event.artifact_update
            assert update.task_id == task_id, f"{skill}: artifact for another Task"
            chunks.extend(texts(update.artifact.parts))
            continue
        assert event.HasField("status_update"), f"{skill}: unexpected event {event}"
        update = event.status_update
        assert update.task_id == task_id, f"{skill}: status for another Task"
        state = update.status.state
        ended = state == terminal
        assert ended or state in (TASK_STATE_SUBMITTED, TASK_STATE_WORKING), (
            f"{skill}: unexpected state {state}"
        )
        chunks.extend(texts(update.status.message.parts))
    assert ended, f"{skill}: stream closed before the expected terminal status"
    if skill == "stream":
        assert chunks == ["one", "two", "three"], chunks


async def check(url, binding):
    if not __debug__:
        raise RuntimeError("Run this probe without Python optimization")
    async with httpx.AsyncClient(
        headers={"X-API-Key": "interop-secret", "A2A-Version": "1.0"},
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    ) as http:

        async def discover(streaming):
            config = ClientConfig(
                httpx_client=http,
                supported_protocol_bindings=[binding],
                streaming=streaming,
            )
            return await ClientFactory(config).create_from_url(url)

        client = await discover(streaming=False)
        (immediate,) = [
            e async for e in client.send_message(message("greet", text="hello"))
        ]
        assert immediate.HasField("message") and immediate.message.role == ROLE_AGENT
        assert texts(immediate.message.parts) == ["hello"], "Wrong greeting"

        (response,) = [e async for e in client.send_message(message("taskProbe"))]
        assert response.HasField("task") and response.task.id, (
            "taskProbe did not return a Task"
        )
        task = response.task
        assert task.status.state == TASK_STATE_COMPLETED
        result = texts(task.status.message.parts)
        for artifact in task.artifacts:
            result.extend(texts(artifact.parts))
        assert task.id in result, "taskProbe did not receive the returned Task ID"
        read = await client.get_task(GetTaskRequest(id=task.id))
        assert read.id == task.id and read.status.state == TASK_STATE_COMPLETED

        try:
            await client.get_task(GetTaskRequest(id=uuid4().hex))
        except TaskNotFoundError:
            pass
        else:
            raise AssertionError("GetTask accepted a missing task")

        streaming = await discover(streaming=True)
        await check_stream(streaming, "stream", TASK_STATE_COMPLETED)
        await check_stream(streaming, "fail", TASK_STATE_FAILED)
    return {
        "sdk": "a2a-sdk",
        "sdkVersion": version("a2a-sdk"),
        "binding": binding,
        "message": True,
        "task": True,
        "taskRead": True,
        "taskNotFound": True,
        "stream": True,
        "failure": True,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument(
        "--binding", choices=["JSONRPC", "HTTP+JSON"], default="JSONRPC"
    )
    args = parser.parse_args()
    print("A2A_LITE_OFFICIAL " + json.dumps(asyncio.run(check(args.url, args.binding))))
