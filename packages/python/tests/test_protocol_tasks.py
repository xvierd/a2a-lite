"""Task mode exposes only the real protocol task identity."""

import json
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from a2a_lite import Agent, TaskContext


def rpc(client, method, params):
    return client.post(
        "/",
        headers={"A2A-Version": "1.0"},
        json={"jsonrpc": "2.0", "id": uuid4().hex, "method": method, "params": params},
    ).json()


def invoke(client, skill):
    return rpc(
        client,
        "SendMessage",
        {
            "message": {
                "messageId": uuid4().hex,
                "role": "ROLE_USER",
                "parts": [{"text": json.dumps({"skill": skill, "params": {}})}],
            }
        },
    )


@pytest.mark.parametrize("local_store", [None, "memory"])
def test_task_context_is_protocol_identity_without_separate_store(local_store):
    agent = Agent(name="Tasks", description="Protocol identities", task_store=local_store)

    @agent.skill("work")
    async def work(task: TaskContext):
        await task.update("working", "halfway", progress=0.5)
        return {"task_id": task.task_id}

    with TestClient(agent.get_app()) as client:
        task = invoke(client, "work")["result"]["task"]
        payload = json.loads(task["artifacts"][0]["parts"][0]["text"])
        assert payload["task_id"] == task["id"]
        assert rpc(client, "GetTask", {"id": task["id"]})["result"]["status"]["state"] == "TASK_STATE_COMPLETED"


def test_explicit_task_mode_and_message_mode():
    agent = Agent(name="Tasks", description="Explicit task mode")

    @agent.skill("tracked", task=True)
    async def tracked():
        return {"answer": 42}

    @agent.skill("simple")
    async def simple():
        return "hello"

    with TestClient(agent.get_app()) as client:
        response = invoke(client, "tracked")
        task = response["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_COMPLETED"
        assert json.loads(task["artifacts"][0]["parts"][0]["text"]) == {"answer": 42}
        assert "message" in invoke(client, "simple")["result"]


def test_task_failure_is_persisted_without_message_after_task():
    agent = Agent(name="Tasks", description="Failure state")

    @agent.skill("fail", task=True)
    async def fail():
        raise ValueError("test failure")

    with TestClient(agent.get_app()) as client:
        task = invoke(client, "fail")["result"]["task"]
        assert task["status"]["state"] == "TASK_STATE_FAILED"
        assert rpc(client, "GetTask", {"id": task["id"]})["result"]["status"]["state"] == "TASK_STATE_FAILED"
