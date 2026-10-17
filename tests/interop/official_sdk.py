"""Exercise the official Python SDK transport against any Lite JSON-RPC server."""

import argparse
import asyncio
import json
from uuid import uuid4

import httpx
from google.protobuf.json_format import ParseDict

from a2a.client.transports.jsonrpc import JsonRpcTransport
from a2a.types.a2a_pb2 import (
    AgentCard,
    GetTaskRequest,
    SendMessageRequest,
    TASK_STATE_COMPLETED,
)


def message(skill, **params):
    return ParseDict(
        {
            "message": {
                "messageId": uuid4().hex,
                "role": "ROLE_USER",
                "parts": [
                    {"text": json.dumps({"skill": skill, "params": params})},
                ],
            }
        },
        SendMessageRequest(),
    )


async def check(url):
    async with httpx.AsyncClient(
        headers={"X-API-Key": "interop-secret", "A2A-Version": "1.0"},
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    ) as http:
        response = await http.get(url + "/.well-known/agent-card.json")
        response.raise_for_status()
        card = ParseDict(response.json(), AgentCard())
        client = JsonRpcTransport(http, card, url)
        immediate = await client.send_message(message("greet", text="hello"))
        assert immediate.HasField("message"), "greet must be an immediate Message"
        task_response = await client.send_message(message("taskProbe"))
        assert task_response.HasField("task") and task_response.task.id, (
            "taskProbe must return a real Task"
        )
        task = await client.get_task(GetTaskRequest(id=task_response.task.id))
        assert (
            task.id == task_response.task.id
            and task.status.state == TASK_STATE_COMPLETED
        )
        events = [
            event async for event in client.send_message_streaming(message("stream"))
        ]
        assert events and events[0].HasField("task"), "SSE initial snapshot missing"
        assert any(
            event.HasField("status_update")
            and event.status_update.status.state == TASK_STATE_COMPLETED
            for event in events
        ), "SSE completion missing"
        print(
            "A2A_LITE_OFFICIAL "
            + json.dumps(
                {
                    "sdk": "a2a-sdk",
                    "message": True,
                    "task": True,
                    "taskRead": True,
                    "stream": True,
                }
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    asyncio.run(check(parser.parse_args().url))
