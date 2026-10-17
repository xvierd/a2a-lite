import asyncio
import json
from uuid import uuid4

import httpx
import pytest
from starlette.testclient import TestClient

from a2a_lite import Agent, RuntimeConfig
from a2a_lite.auth import APIKeyAuth, CompositeAuth, NoAuth


def payload(skill="work", configuration=None):
    params = {
        "message": {
            "messageId": uuid4().hex,
            "role": "ROLE_USER",
            "parts": [{"text": json.dumps({"skill": skill, "params": {}})}],
        }
    }
    if configuration:
        params["configuration"] = configuration
    return {"jsonrpc": "2.0", "id": uuid4().hex, "method": "SendMessage", "params": params}


def test_profile_validation_and_noauth_fallback():
    for profile in ("authenticated", "durable"):
        with pytest.raises(ValueError, match="auth"):
            Agent("secure", "test", runtime=RuntimeConfig(profile=profile))
    with pytest.raises(ValueError, match="PersistenceConfig"):
        Agent("secure", "test", runtime=RuntimeConfig(profile="durable"), auth=APIKeyAuth(keys=["key"]))
    agent = Agent("secure", "test", runtime=RuntimeConfig(profile="authenticated"), auth=CompositeAuth([NoAuth()]))
    with TestClient(agent.get_app()) as client:
        assert client.post("/", json=payload()).status_code == 401


@pytest.mark.parametrize(
    "kwargs",
    [{"max_concurrent_tasks": 0}, {"max_output_bytes": True}, {"execution_timeout": float("inf")}, {"profile": "prod"}],
)
def test_invalid_limits(kwargs):
    with pytest.raises(ValueError):
        RuntimeConfig(**kwargs)


async def test_admission_covers_detached_task_and_deadline():
    agent = Agent("bounded", "test", runtime=RuntimeConfig(max_concurrent_tasks=1, execution_timeout=0.05))
    started = asyncio.Event()

    @agent.skill("work", task=True)
    async def work():
        started.set()
        await asyncio.sleep(10)

    app = agent.get_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"A2A-Version": "1.0"}
        ) as client,
    ):
        first = (await client.post("/", json=payload(configuration={"returnImmediately": True}))).json()["result"][
            "task"
        ]
        await started.wait()
        second = (await client.post("/", json=payload())).json()["result"]["task"]
        assert second["status"]["state"] == "TASK_STATE_REJECTED"
        await asyncio.sleep(0.08)
        response = (
            await client.post(
                "/", json={"jsonrpc": "2.0", "id": "get", "method": "GetTask", "params": {"id": first["id"]}}
            )
        ).json()
        assert response["result"]["status"]["state"] == "TASK_STATE_FAILED"
        stats = app.state.runtime.state.snapshot()
        assert stats["rejected"] == stats["timed_out"] == 1
        assert stats["active"] == 0


async def test_body_output_limits_hooks_and_readiness():
    agent = Agent("bounded", "test", runtime=RuntimeConfig(max_request_bytes=400, max_event_bytes=300))
    events = []

    @agent.on_startup
    async def startup():
        events.append(("start", asyncio.get_running_loop()))

    @agent.on_shutdown
    async def shutdown():
        events.append(("stop", asyncio.get_running_loop()))

    @agent.skill("work", task=True)
    async def work():
        return "x" * 1000

    app = agent.get_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"A2A-Version": "1.0"}
    ) as client:
        assert (await client.get("/health/ready")).status_code == 503
        async with app.router.lifespan_context(app):
            assert (await client.get("/health/ready")).json() == {"ready": True}

            async def chunks():
                yield b"x" * 200
                yield b"x" * 300

            assert (await client.post("/", content=chunks())).status_code == 413
            task = (await client.post("/", json=payload())).json()["result"]["task"]
            assert task["status"]["state"] == "TASK_STATE_FAILED"
        assert (await client.get("/health/ready")).status_code == 503
    assert [e[0] for e in events] == ["start", "stop"]
    assert events[0][1] is events[1][1]


async def test_shutdown_cancels_work_and_closes_once():
    agent = Agent("bounded", "test", runtime=RuntimeConfig(shutdown_timeout=0.02))
    stopped = asyncio.Event()

    @agent.skill("work", task=True)
    async def work():
        try:
            await asyncio.sleep(100)
        finally:
            stopped.set()

    app = agent.get_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"A2A-Version": "1.0"}
        ) as client,
    ):
        await client.post("/", json=payload(configuration={"returnImmediately": True}))
    assert stopped.is_set()
    assert app.state.runtime.state.snapshot()["active"] == 0
    await app.state.runtime.stop()


async def test_embedded_servers_preserve_signal_handlers_and_stop_independently():
    import signal

    before = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    agent = Agent("embedded", "test")

    @agent.skill("work")
    async def work():
        return "ok"

    one, two = await agent.start(), await agent.start()
    try:
        assert {sig: signal.getsignal(sig) for sig in before} == before
        async with httpx.AsyncClient() as client:
            assert (await client.get(one.url + "/health/ready")).status_code == 200
        await one.stop()
        assert not one.ready and two.ready
        assert one.stats["accepting"] is False
    finally:
        await one.stop()
        await two.stop()


async def test_passive_stream_limit_and_history_retention():
    from a2a.server.context import ServerCallContext
    from a2a.server.tasks import InMemoryTaskStore
    from a2a.types import Artifact, Message, Task

    from a2a_lite.stores import bound_task_store

    config = RuntimeConfig(max_streams=1, max_history_messages=2, max_artifacts=1)
    agent = Agent("bounded", "test", runtime=config)
    handler = agent._build_request_handler(agent.build_agent_card())
    from a2a.utils.errors import UnsupportedOperationError

    async with handler._stream_slot():
        with pytest.raises(UnsupportedOperationError, match="capacity"):
            async with handler._stream_slot():
                pass
    assert handler.runtime.state.streams == 0
    store = bound_task_store(InMemoryTaskStore(), config)
    task = Task(
        id="id",
        context_id="context",
        history=[Message(message_id=str(i)) for i in range(5)],
        artifacts=[Artifact(artifact_id=str(i)) for i in range(3)],
    )
    await store.save(task, ServerCallContext())
    saved = await store.get("id", ServerCallContext())
    assert [m.message_id for m in saved.history] == ["3", "4"]
    assert [a.artifact_id for a in saved.artifacts] == ["2"]
    await handler.runtime.stop()


async def test_per_principal_admission_keeps_other_users_available():
    agent = Agent(
        "bounded",
        "test",
        runtime=RuntimeConfig(max_per_principal=1),
        auth=APIKeyAuth(principals={"a": "alice", "b": "bob"}),
    )
    gate = asyncio.Event()

    @agent.skill("work", task=True)
    async def work():
        await gate.wait()
        return "done"

    app = agent.get_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"A2A-Version": "1.0"}
        ) as client,
    ):
        first = await client.post(
            "/", json=payload(configuration={"returnImmediately": True}), headers={"X-API-Key": "a"}
        )
        assert "task" in first.json()["result"]
        rejected = await client.post("/", json=payload(), headers={"X-API-Key": "a"})
        assert rejected.json()["result"]["task"]["status"]["state"] == "TASK_STATE_REJECTED"
        other = await client.post(
            "/", json=payload(configuration={"returnImmediately": True}), headers={"X-API-Key": "b"}
        )
        assert other.json()["result"]["task"]["status"]["state"] != "TASK_STATE_REJECTED"
        gate.set()


async def test_memory_retention_evicts_only_terminal_and_expires_ttl():
    from a2a.server.context import ServerCallContext
    from a2a.server.tasks import InMemoryTaskStore
    from a2a.types import Task, TaskState, TaskStatus

    from a2a_lite.stores import bound_task_store

    config = RuntimeConfig(max_stored_tasks=1, task_ttl=0.02)
    store = bound_task_store(InMemoryTaskStore(), config)
    ctx = ServerCallContext()
    first = Task(id="first", context_id="ctx", status=TaskStatus(state=TaskState.TASK_STATE_WORKING))
    second = Task(id="second", context_id="ctx", status=TaskStatus(state=TaskState.TASK_STATE_COMPLETED))
    await store.save(first, ctx)
    with pytest.raises(RuntimeError, match="capacity"):
        await store.save(second, ctx)
    first.status.state = TaskState.TASK_STATE_COMPLETED
    await store.save(first, ctx)
    await store.save(second, ctx)
    assert await store.get("first", ctx) is None
    await asyncio.sleep(0.03)
    assert await store.get("second", ctx) is None
