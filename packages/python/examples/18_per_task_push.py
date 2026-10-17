"""Register a callback when starting a real A2A task.

Terminal 1: A2A_AGENT_KEY=your-key python examples/18_per_task_push.py --serve
Terminal 2: A2A_AGENT_KEY=your-key A2A_CALLBACK_URL=https://your-public-host/webhook \\
            python examples/18_per_task_push.py

Callbacks require public HTTPS. To use a local receiver, expose it through
an HTTPS reverse proxy; loopback/private callback destinations are rejected.
The receiver gets standard A2A task/status/artifact events.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from uuid import uuid4

import httpx

from a2a_lite import Agent
from a2a_lite.auth import APIKeyAuth

worker = Agent(
    name="WorkerAgent", description="Processes data slowly", auth=APIKeyAuth(keys=[os.environ["A2A_AGENT_KEY"]])
)


@worker.skill("process", streaming=True)
async def process(data: str):
    await asyncio.sleep(3)
    yield json.dumps({"processed": data.upper(), "length": len(data)})


async def main():
    callback_url = os.environ["A2A_CALLBACK_URL"]
    callback = {"url": callback_url}
    if token := os.getenv("A2A_CALLBACK_TOKEN"):
        callback["authentication"] = {"scheme": "Bearer", "credentials": token}

    # Register at task creation so even fast tasks cannot finish before the
    # callback exists. A message-only response does not have a trackable task.
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8787/",
            headers={"A2A-Version": "1.0", "X-API-Key": os.environ["A2A_AGENT_KEY"]},
            json={
                "jsonrpc": "2.0",
                "id": uuid4().hex,
                "method": "SendMessage",
                "params": {
                    "configuration": {
                        "returnImmediately": True,
                        "taskPushNotificationConfig": callback,
                    },
                    "message": {
                        "messageId": uuid4().hex,
                        "role": "ROLE_USER",
                        "parts": [{"text": json.dumps({"skill": "process", "params": {"data": "hello"}})}],
                    },
                },
            },
        )
        response.raise_for_status()
        result = response.json()
        if "error" in result:
            raise RuntimeError(result["error"])
        print(f"Task submitted: {result['result']['task']['id']}")
        print("The configured HTTPS receiver will receive task updates.")


if __name__ == "__main__":
    if "--serve" in sys.argv:
        worker.run(port=8787)
    else:
        asyncio.run(main())
