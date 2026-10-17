"""Real SQLite and optional real PostgreSQL state/outbox/restart contracts."""

import asyncio
import os
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest
from a2a.server.cluster.task_store import ConcurrentTaskModificationError
from a2a.server.cluster.version import TaskVersion
from a2a.server.context import ServerCallContext
from a2a.types import Task, TaskPushNotificationConfig, TaskState, TaskStatus
from cryptography.fernet import Fernet
from sqlalchemy import select, text, update
from sqlalchemy.exc import DBAPIError

from a2a_lite import Agent, PersistenceConfig, RuntimeConfig
from a2a_lite.auth import APIKeyAuth, AuthResult
from a2a_lite.server import AuthenticatedUser
from tests.test_managed_runtime import payload


@pytest.fixture(params=["sqlite", "postgresql"])
async def config(request, tmp_path):
    schema = None
    if request.param == "postgresql":
        url = os.getenv("A2ALITE_POSTGRES_DSN")
        if not url:
            pytest.skip("Set A2ALITE_POSTGRES_DSN for real PostgreSQL contracts")
        schema = "py_test_" + uuid4().hex
    else:
        url = "sqlite+aiosqlite:///" + str(tmp_path / "state.db")
    config = PersistenceConfig(
        url, Fernet.generate_key(), schema=schema, dispatch_callbacks=False, callback_retry_delay=0.001
    )
    yield config
    if schema:
        backend = config.build()
        async with backend.engine.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await backend.close()


def context(tenant="a", user="alice"):
    result = AuthResult.success(user, authorized_tenants={tenant})
    return ServerCallContext(user=AuthenticatedUser(result, tenant), tenant=tenant, state={"auth_result": result})


async def seed(backend, ctx=None):
    ctx = ctx or context()
    task = Task(id=str(uuid4()), context_id=str(uuid4()), status=TaskStatus(state=TaskState.TASK_STATE_WORKING))
    cfg = TaskPushNotificationConfig(
        id="callback", url="https://callback.example/result?SECRET=query", token="SECRET_TOKEN"
    )
    await backend.push_store.set_info(task.id, cfg, context=ctx)
    version = await backend.task_store.save(task, event=task, prev=None, prev_version=TaskVersion.MISSING, context=ctx)
    return task, version, cfg


async def test_explicit_schema_restart_owner_and_cas(config):
    backend = config.build()
    with pytest.raises(RuntimeError, match="schema"):
        await backend.start()
    await config.migrate()
    await backend.start()
    task, version, _ = await seed(backend)
    assert await backend.task_store.get(task.id, context("b")) is None
    assert await backend.task_store.get(task.id, context(user="bob")) is None
    with pytest.raises(ConcurrentTaskModificationError):
        await backend.task_store.save(task, event=task, prev=task, prev_version=TaskVersion.MISSING, context=context())
    assert (await backend.callback_stats()) == {"pending": 1}
    await backend.close()
    restarted = config.build()
    await restarted.start()
    assert (await restarted.task_store.get(task.id, context())).task.id == task.id
    assert (await restarted.push_store.get_info(task.id, context=context()))[0].token == "SECRET_TOKEN"
    assert await restarted.push_store.get_info(task.id, context=context("b")) == []
    async with restarted.engine.begin() as conn:
        await conn.execute(update(restarted.schema_table).values(version=999))
    with pytest.raises(RuntimeError, match="schema"):
        await restarted.check()
    with pytest.raises(RuntimeError, match="version"):
        await config.migrate()
    await restarted.close()


async def test_atomic_handoff_leases_retry_deadletter_delete_rotation(config, monkeypatch):
    await config.migrate()
    one, two = config.build(), config.build()
    await one.start()
    await two.start()
    task, version, cfg = await seed(one)
    row1, row2 = await asyncio.gather(one._claim(), two._claim())
    assert sum(row is not None for row in (row1, row2)) == 1
    row = row1 or row2
    assert b"SECRET" not in row["config_data"]
    assert row["config_data"].startswith(b"a2a-lite:v1:default:")
    # Process loss before delivery: lease expiry recovers the same durable row.
    async with one.engine.begin() as conn:
        await conn.execute(update(one.outbox).values(lease_until=0))
    calls = []

    async def fake_deliver(item):
        calls.append(item["id"])
        return False

    monkeypatch.setattr(two, "_deliver", fake_deliver)
    for _ in range(config.callback_attempts):
        async with one.engine.begin() as conn:
            await conn.execute(update(one.outbox).values(due=0))
        await two.dispatch_once()
    assert await one.callback_stats() == {"dead": 1}
    assert len(set(calls)) == 1
    assert await one.retry_dead(row["id"])
    # Rotation keeps config and queued encrypted snapshots readable with new key.
    rotated_config = replace(
        config,
        encryption_key=Fernet.generate_key(),
        encryption_key_id="next",
        previous_encryption_keys={"default": config.encryption_key},
    )
    rotated = rotated_config.build()
    await rotated.rotate_encryption()
    new_only = replace(rotated_config, previous_encryption_keys={}).build()
    assert (await new_only.push_store.get_info(task.id, context=context()))[0].token == cfg.token
    await one.push_store.delete_info(task.id, context=context(), config_id=cfg.id)
    assert await one.callback_stats() == {"canceled": 1}
    assert not await one.dispatch_once()
    await asyncio.gather(one.close(), two.close(), rotated.close(), new_only.close())


async def test_sdk_event_stream_two_replicas_and_task_write_rollback(config):
    await config.migrate()
    one, two = config.build(), config.build()
    await one.start()
    await two.start()
    task, version, _ = await seed(one)
    stream = two.event_stream.subscribe(task.id, after=version)
    waiting = asyncio.create_task(anext(stream))
    changed = Task()
    changed.CopyFrom(task)
    changed.status.state = TaskState.TASK_STATE_COMPLETED
    next_version = await one.task_store.save(changed, event=changed, prev=task, prev_version=version, context=context())
    event = await asyncio.wait_for(waiting, 2)
    assert event.event.status.state == TaskState.TASK_STATE_COMPLETED
    assert event.version == next_version
    await stream.aclose()
    assert (await one.callback_stats()) == {"pending": 2}
    # A failing outbox insert rolls back the SDK snapshot/version/event transaction.
    async with one.engine.begin() as conn:
        await conn.execute(text("DROP TABLE a2a_lite_outbox"))
    with pytest.raises(DBAPIError):
        await one.task_store.save(task, event=task, prev=changed, prev_version=next_version, context=context())
    assert (await two.task_store.get(task.id, context())).task.status.state == TaskState.TASK_STATE_COMPLETED
    await asyncio.gather(one.close(), two.close())


async def test_durable_http_restart_and_readiness(config):
    await config.migrate()

    def create():
        agent = Agent(
            "durable",
            "test",
            auth=APIKeyAuth(principals={"key": "alice", "other": "bob"}),
            runtime=RuntimeConfig(profile="durable"),
            persistence=config,
        )

        @agent.skill("work", task=True)
        async def work():
            return "persisted"

        return agent.get_app()

    first = create()
    headers = {"A2A-Version": "1.0", "X-API-Key": "key"}
    async with (
        first.router.lifespan_context(first),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=first), base_url="http://test", headers=headers) as client,
    ):
        task = (await client.post("/", json=payload())).json()["result"]["task"]
    second = create()
    async with (
        second.router.lifespan_context(second),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=second), base_url="http://test", headers=headers) as client,
    ):
        body = {"jsonrpc": "2.0", "id": "get", "method": "GetTask", "params": {"id": task["id"]}}
        assert (await client.post("/", json=body)).json()["result"]["id"] == task["id"]
        assert "error" in (await client.post("/", json=body, headers={"X-API-Key": "other"})).json()
        assert (await client.get("/health/ready")).status_code == 200
        async with second.state.runtime.backend.engine.begin() as conn:
            await conn.execute(update(second.state.runtime.backend.schema_table).values(version=999))
        assert (await client.get("/health/ready")).status_code == 503


async def test_checkpoint_recovery_fences_stale_writer_and_transactional_effect(config):
    from a2a.server.agent_execution import RequestContext
    from a2a.types import Message, Part, SendMessageRequest

    from a2a_lite import TaskContext
    from a2a_lite.recovery import EXECUTION_KEY, ExecutionLease, ExecutionLeaseLostError
    from tests.test_protocol_tasks import json

    await config.migrate()
    agent = Agent(
        "recoverable",
        "test",
        auth=APIKeyAuth(principals={"key": "alice"}, authorized_tenants={"a"}),
        runtime=RuntimeConfig(profile="durable"),
        persistence=config,
    )
    seen = []

    async def protected_effect(conn):
        await conn.execute(text("UPDATE test_effect_ledger SET value=value+1"))
        return "saved"

    @agent.skill("work", recoverable=True)
    async def work(task: TaskContext):
        seen.append(task.checkpoint_data)
        assert await task.effect_once("protected", protected_effect) == "saved"
        await task.checkpoint({"step": 2})
        return "recovered"

    app = agent.get_app()
    one = app.state.runtime.backend
    two = config.build()
    # Deterministic manual reconciliation rather than a background polling race.
    executor = one.recovery.executor
    one.recovery.executor = None
    await one.start()
    await two.start()
    async with one.engine.begin() as conn:
        await conn.execute(text("CREATE TABLE test_effect_ledger (value INTEGER NOT NULL)"))
        await conn.execute(text("INSERT INTO test_effect_ledger VALUES (0)"))
    task = Task(id=str(uuid4()), context_id=str(uuid4()), status=TaskStatus(state=TaskState.TASK_STATE_WORKING))
    call_context = context()
    request = SendMessageRequest(
        message=Message(message_id=str(uuid4()), role=1, parts=[Part(text=json.dumps({"skill": "work", "params": {}}))])
    )
    request_context = RequestContext(call_context, request=request, task_id=task.id, context_id=task.context_id)
    lease = await one.recovery.enter(request_context, True)
    version = await one.task_store.save(
        task, event=task, prev=None, prev_version=TaskVersion.MISSING, context=call_context
    )
    assert await lease.effect_once("protected", protected_effect) == "saved"
    await lease.checkpoint({"step": 1})
    # Crash after the effect and checkpoint, before task completion.
    await one.recovery.close()
    async with one.engine.begin() as conn:
        await conn.execute(update(one.executions).values(lease_until=0))
    row = await two.recovery.claim()
    assert row["fence"] != lease.fence
    with pytest.raises(ExecutionLeaseLostError):
        await lease.effect_once("stale", protected_effect)
    with pytest.raises(ExecutionLeaseLostError):
        await one.task_store.save(task, event=task, prev=task, prev_version=version, context=call_context)
    # The database trigger independently rejects stale writes bypassing the adapter.
    from a2a.server.cluster.database_task_store import VersionedDatabaseTaskStore

    from a2a_lite.persistence import _sql_owner

    raw_store = VersionedDatabaseTaskStore(one.engine, create_table=False, owner_resolver=_sql_owner)
    changed = Task()
    changed.CopyFrom(task)
    changed.status.state = TaskState.TASK_STATE_COMPLETED
    with pytest.raises(DBAPIError, match="Execution lease lost"):
        await raw_store.save(changed, event=changed, prev=task, prev_version=version, context=call_context)
    # A second runtime resumes the explicitly recoverable skill from the checkpoint.
    two.recovery.executor = executor
    executor.recovery = two.recovery
    await two.recovery.resume(row)
    recovered = await two.task_store.get(task.id, context())
    assert recovered.task.status.state == TaskState.TASK_STATE_COMPLETED
    assert recovered.task.artifacts[-1].parts[0].text == "recovered"
    assert seen == [{"step": 1}]
    async with two.engine.connect() as conn:
        assert (await conn.execute(text("SELECT value FROM test_effect_ledger"))).scalar_one() == 1
    await asyncio.gather(one.close(), two.close())


async def test_unrecoverable_execution_becomes_explicit_interruption(config):
    from a2a.server.agent_execution import RequestContext
    from a2a.types import Message, Part, SendMessageRequest

    await config.migrate()
    backend = config.build()
    await backend.start()
    task = Task(id=str(uuid4()), context_id=str(uuid4()), status=TaskStatus(state=TaskState.TASK_STATE_WORKING))
    ctx = context()
    request = SendMessageRequest(message=Message(message_id=str(uuid4()), role=1, parts=[Part(text="work")]))
    lease = await backend.recovery.enter(
        RequestContext(ctx, request=request, task_id=task.id, context_id=task.context_id), False
    )
    await backend.task_store.save(task, event=task, prev=None, prev_version=TaskVersion.MISSING, context=ctx)
    await backend.recovery.close()
    async with backend.engine.begin() as conn:
        await conn.execute(update(backend.executions).values(lease_until=0))
    row = await backend.recovery.claim()
    await backend.recovery.resume(row)
    stored = await backend.task_store.get(task.id, context())
    assert stored.task.status.state == TaskState.TASK_STATE_FAILED
    assert "does not support recovery" in stored.task.status.message.parts[0].text
    await backend.close()


async def test_callback_wire_dedup_expiry_and_missing_trigger(config, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from a2a_lite import push_notifications

    await config.migrate()
    backend = config.build()
    await backend.start()
    task, _, cfg = await seed(backend)
    wire = AsyncMock(return_value=True)
    backend._client = SimpleNamespace(post_callback=wire, aclose=AsyncMock())
    monkeypatch.setattr(push_notifications, "validate_callback_url", AsyncMock(return_value=True))
    first = await backend._claim()
    assert await backend._deliver(first)
    async with backend.engine.begin() as conn:
        await conn.execute(update(backend.outbox).values(lease_until=0))
    assert await backend.dispatch_once()
    assert len(wire.call_args_list) == 2
    headers = [call.kwargs["headers"] for call in wire.call_args_list]
    assert headers[0]["X-A2A-Delivery-Id"] == headers[1]["X-A2A-Delivery-Id"]
    assert headers[0]["Content-Type"] == "application/a2a+json"
    assert headers[0]["X-A2A-Notification-Token"] == cfg.token
    assert "task" in wire.call_args.kwargs["json"]
    assert await backend.callback_stats() == {"delivered": 1}
    # An aged queued delivery expires without contacting its destination.
    async with backend.engine.begin() as conn:
        await conn.execute(update(backend.outbox).values(status="pending", created_at=0, due=0))
    assert not await backend.dispatch_once()
    assert await backend.callback_stats() == {"dead": 1}
    assert len(wire.call_args_list) == 2
    assert await backend.retry_dead(first["id"])
    assert await backend.dispatch_once()
    assert await backend.callback_stats() == {"delivered": 1}
    assert len(wire.call_args_list) == 3
    assert wire.call_args.kwargs["headers"]["X-A2A-Delivery-Id"] == headers[0]["X-A2A-Delivery-Id"]
    async with backend.engine.begin() as conn:
        await conn.execute(
            text(
                "DROP TRIGGER a2a_lite_callback_event ON task_events"
                if backend.engine.dialect.name == "postgresql"
                else "DROP TRIGGER a2a_lite_callback_event"
            )
        )
    with pytest.raises(RuntimeError, match="schema"):
        await backend.check()
    await backend.close()


async def test_distributed_leases_ignore_host_clock_skew(config, monkeypatch):
    import time

    from a2a.server.agent_execution import RequestContext
    from a2a.types import Message, Part, SendMessageRequest

    await config.migrate()
    one, two = config.build(), config.build()
    await one.start()
    await two.start()
    task, _, _ = await seed(one)
    request = SendMessageRequest(message=Message(message_id=str(uuid4()), role=1, parts=[Part(text="work")]))
    monkeypatch.setattr(time, "time", lambda: 1.0)  # writer's wall clock is far behind
    lease = await one.recovery.enter(
        RequestContext(context(), request=request, task_id=task.id, context_id=task.context_id), True
    )
    await lease.checkpoint({"safe": True})
    row = await one._claim()
    assert row is not None
    monkeypatch.setattr(time, "time", lambda: 10**12)  # contender's clock is far ahead
    assert await two.recovery.claim() is None
    assert await two._claim() is None
    await lease.checkpoint({"safe": "still-owned"})
    await asyncio.gather(one.close(), two.close())


async def test_sql_push_limit_and_terminal_cleanup(config):
    from datetime import datetime, timedelta, timezone

    config = replace(config, max_push_configs=1)
    await config.migrate()
    backend = config.build()
    await backend.start()
    task, version, _ = await seed(backend)
    with pytest.raises(DBAPIError, match="limit"):
        await backend.push_store.set_info(
            task.id, TaskPushNotificationConfig(id="second", url="https://other.example"), context=context()
        )
    task.status.state = TaskState.TASK_STATE_COMPLETED
    task.status.timestamp.FromDatetime(datetime.now(timezone.utc))
    await backend.task_store.save(task, event=task, prev=task, prev_version=version, context=context())
    cutoff = datetime.now(timezone.utc) + timedelta(seconds=1)
    assert await backend.cleanup(cutoff) == 0  # queued callback preserves its task
    async with backend.engine.begin() as conn:
        await conn.execute(update(backend.outbox).values(status="delivered"))
    assert await backend.cleanup(cutoff) == 1
    assert await backend.task_store.get(task.id, context()) is None
    assert await backend.cleanup(cutoff) == 0
    await backend.close()


async def test_cleanup_does_not_starve_terminal_tasks_behind_active_tasks(config):
    from datetime import datetime, timedelta, timezone

    from a2a.server.models import TaskModel
    from sqlalchemy import insert

    await config.migrate()
    backend = config.build()
    old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2)
    async with backend.engine.begin() as conn:
        await conn.execute(
            insert(TaskModel.__table__),
            [
                {
                    "id": str(uuid4()),
                    "context_id": str(uuid4()),
                    "last_updated": old,
                    "status": {"state": "TASK_STATE_WORKING"},
                }
                for _ in range(501)
            ]
            + [
                {
                    "id": str(uuid4()),
                    "context_id": str(uuid4()),
                    "last_updated": old + timedelta(hours=1),
                    "status": {"state": "TASK_STATE_COMPLETED"},
                }
            ],
        )
    assert await backend.cleanup(datetime.now(timezone.utc)) == 1
    async with backend.engine.connect() as conn:
        assert len((await conn.execute(select(TaskModel.id))).all()) == 501
    await backend.close()


@pytest.mark.parametrize("paused_state", ["input-required", "auth-required"])
async def test_durable_task_continuation_keeps_identity_and_rejects_other_owner(config, paused_state):
    import json

    from a2a_lite import TaskContext
    from a2a_lite.recovery import ExecutionLeaseLostError

    await config.migrate()
    agent = Agent(
        "continuation",
        "test",
        persistence=config,
        runtime=RuntimeConfig(profile="durable"),
        auth=APIKeyAuth(principals={"key": "alice", "other": "bob"}, authorized_tenants={"", "other"}),
    )
    calls = []
    executions = []

    @agent.skill("work", recoverable=True)
    async def work(task: TaskContext, answer: str = ""):
        calls.append(task.task_id)
        executions.append(task._execution)
        if not answer:
            await task.checkpoint({"awaiting": "answer"})
            await task.update(paused_state, "Please continue")
            return None
        assert task.checkpoint_data == {"awaiting": "answer"}
        return answer

    app = agent.get_app()
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers={"A2A-Version": "1.0", "X-API-Key": "key"},
        ) as client,
    ):
        initial = (await client.post("/", json=payload())).json()["result"]["task"]
        assert initial["status"]["state"] == "TASK_STATE_" + paused_state.upper().replace("-", "_")
        with pytest.raises(ExecutionLeaseLostError):
            await executions[0].checkpoint({"stale": True})
        async with app.state.runtime.backend.engine.begin() as conn:
            await conn.execute(update(app.state.runtime.backend.executions).values(lease_until=0))
        assert await app.state.runtime.backend.recovery.claim() is None  # paused tasks await new input
        continuation = payload()
        continuation["params"]["message"].update(
            taskId=initial["id"],
            contextId=initial["contextId"],
            parts=[{"text": json.dumps({"skill": "work", "params": {"answer": "accepted"}})}],
        )
        denied = (await client.post("/", json=continuation, headers={"X-API-Key": "other"})).json()
        assert "error" in denied
        continuation["params"]["tenant"] = "other"
        assert "error" in (await client.post("/", json=continuation)).json()
        continuation["params"].pop("tenant")
        final = (await client.post("/", json=continuation)).json()["result"]["task"]
        assert final["id"] == initial["id"]
        assert final["status"]["state"] == "TASK_STATE_COMPLETED"
        assert final["artifacts"][-1]["parts"][0]["text"] == "accepted"
        assert calls == [initial["id"], initial["id"]]
        assert executions[0].fence != executions[1].fence
        with pytest.raises(ExecutionLeaseLostError):
            await executions[0].checkpoint({"stale": True})
        assert "error" in (await client.post("/", json=continuation)).json()


async def test_shutdown_bounds_resistant_recovery_runner_and_shutdown_hook(config):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from a2a.server.agent_execution import RequestContext
    from a2a.types import Message, Part, SendMessageRequest

    from a2a_lite.recovery import ExecutionLeaseLostError
    from a2a_lite.runtime import RuntimeLifecycle, RuntimeState

    await config.migrate()
    backend = config.build()
    await backend.start()
    release = asyncio.Event()
    started = asyncio.Event()
    refused = []
    lease_holder = []

    async def resistant_runner():
        request = SendMessageRequest(message=Message(message_id=str(uuid4()), role=1, parts=[Part(text="work")]))
        lease = await backend.recovery.enter(
            RequestContext(context(), request=request, task_id=str(uuid4()), context_id=str(uuid4())), True
        )
        lease_holder.append(lease)
        started.set()
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue
        with pytest.raises(ExecutionLeaseLostError):
            await lease.checkpoint({"too_late": True})
        refused.append(True)

    async def resistant_hook():
        while not release.is_set():
            try:
                await release.wait()
            except asyncio.CancelledError:
                continue

    runner = asyncio.create_task(resistant_runner())
    backend.recovery._runners.add(runner)
    await started.wait()
    state = RuntimeState(RuntimeConfig(shutdown_timeout=0.03))
    lifecycle = RuntimeLifecycle(
        SimpleNamespace(_on_shutdown=[resistant_hook]), SimpleNamespace(aclose=AsyncMock()), state, backend
    )
    try:
        await asyncio.wait_for(lifecycle.stop(), 0.5)
        assert state.uncooperative >= 1
        assert not runner.done()
        # The old token is revoked before pool disposal or returning shutdown.
        async with backend.engine.connect() as conn:
            row = (await conn.execute(select(backend.executions))).mappings().one()
            assert row["fence"] != lease_holder[0].fence
            assert row["lease_until"] == 0
    finally:
        release.set()
        await asyncio.wait_for(runner, 1)
        await asyncio.sleep(0)
        await backend.engine.dispose()
    assert refused == [True]


async def test_stale_producer_cancellation_cannot_bypass_transactional_fence(config, monkeypatch):
    from a2a.server.agent_execution import RequestContext
    from a2a.server.cluster.database_task_store import VersionedDatabaseTaskStore
    from a2a.types import Message, Part, SendMessageRequest

    from a2a_lite.recovery import CANCEL_KEY

    await config.migrate()
    backend = config.build()
    ctx = context()
    task = Task(id=str(uuid4()), context_id=str(uuid4()), status=TaskStatus(state=TaskState.TASK_STATE_WORKING))
    request = SendMessageRequest(message=Message(message_id=str(uuid4()), role=1, parts=[Part(text="work")]))
    lease = await backend.recovery.enter(
        RequestContext(ctx, request=request, task_id=task.id, context_id=task.context_id), True
    )
    version = await backend.task_store.save(task, event=task, prev=None, prev_version=TaskVersion.MISSING, context=ctx)
    original_save = VersionedDatabaseTaskStore.save
    replacement_fence = str(uuid4())

    async def replace_between_precheck_and_commit(store, task, **kwargs):
        async with backend.engine.begin() as conn:
            await conn.execute(
                update(backend.executions)
                .where(backend.executions.c.task_id == task.id)
                .values(fence=replacement_fence)
            )
        return await original_save(store, task, **kwargs)

    task.status.state = TaskState.TASK_STATE_CANCELED
    monkeypatch.setattr(VersionedDatabaseTaskStore, "save", replace_between_precheck_and_commit)
    with pytest.raises(DBAPIError, match="Execution lease lost"):
        await backend.task_store.save(task, event=task, prev=task, prev_version=version, context=ctx)
    assert (await backend.task_store.get(task.id, context())).task.status.state == TaskState.TASK_STATE_WORKING
    assert lease.fence != replacement_fence
    # A separately authorized CancelTask remains authoritative after transfer.
    monkeypatch.setattr(VersionedDatabaseTaskStore, "save", original_save)
    cancel_context = context()
    cancel_context.state[CANCEL_KEY] = True
    await backend.task_store.save(task, event=task, prev=task, prev_version=version, context=cancel_context)
    assert (await backend.task_store.get(task.id, context())).task.status.state == TaskState.TASK_STATE_CANCELED
    await backend.close()
