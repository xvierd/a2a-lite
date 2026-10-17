"""Tests for the EXPERIMENTAL gRPC transport (agent.run_grpc / build_grpc_server).

Skipped entirely when the optional grpc extra is not installed:
pip install a2a-lite[grpc]
"""

import asyncio
import json
import socket

import pytest

from a2a_lite import Agent
from a2a_lite.auth import APIKeyAuth, NoAuth

try:
    import grpc
    from a2a.types import a2a_pb2, a2a_pb2_grpc

    HAS_GRPC = True
except ImportError:
    HAS_GRPC = False

pytestmark = pytest.mark.skipif(not HAS_GRPC, reason="a2a-lite[grpc] extra not installed")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _echo_agent() -> Agent:
    agent = Agent(name="GrpcEchoBot", description="Echo bot over gRPC")

    @agent.skill("echo")
    async def echo(message: str) -> str:
        return f"echo: {message}"

    return agent


def _send_message_request(text: str):
    return a2a_pb2.SendMessageRequest(
        message=a2a_pb2.Message(
            message_id="m1",
            role=a2a_pb2.ROLE_USER,
            parts=[a2a_pb2.Part(text=text)],
        )
    )


def test_agent_card_advertises_grpc_interface_only_when_enabled():
    agent = _echo_agent()

    card = agent.build_agent_card("localhost", 8787, grpc_url="localhost:50051")
    grpc_ifaces = [i for i in card.supported_interfaces if i.protocol_binding == "GRPC"]
    assert len(grpc_ifaces) == 1
    assert grpc_ifaces[0].url == "localhost:50051"
    assert grpc_ifaces[0].protocol_version == "1.0"

    card_http_only = agent.build_agent_card("localhost", 8787)
    assert all(i.protocol_binding != "GRPC" for i in card_http_only.supported_interfaces)


async def test_grpc_send_message_roundtrip():
    """Real gRPC server + SDK-generated stub: SendMessage returns the skill result."""
    agent = _echo_agent()
    port = _free_port()
    server = agent.build_grpc_server("127.0.0.1", port)
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = a2a_pb2_grpc.A2AServiceStub(channel)
            request = _send_message_request(json.dumps({"skill": "echo", "params": {"message": "hi"}}))
            response = await stub.SendMessage(request)
        assert response.HasField("message")
        assert response.message.role == a2a_pb2.ROLE_AGENT
        assert response.message.parts[0].text == "echo: hi"
    finally:
        await server.stop(grace=1)


async def test_grpc_authentication_task_ownership_and_card():
    agent = Agent(name="Private", description="Private tasks", auth=APIKeyAuth(keys=["alice", "bob"]))

    @agent.skill("work", streaming=True)
    async def work():
        yield "done"

    port = _free_port()
    server = agent.build_grpc_server("127.0.0.1", port)
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = a2a_pb2_grpc.A2AServiceStub(channel)
            request = _send_message_request(json.dumps({"skill": "work", "params": {}}))
            with pytest.raises(grpc.aio.AioRpcError) as missing_auth:
                await stub.SendMessage(request)
            assert missing_auth.value.code() == grpc.StatusCode.UNAUTHENTICATED

            response = await stub.SendMessage(request, metadata=[("x-api-key", "alice")])
            task_id = response.task.id
            assert task_id
            assert (
                await stub.GetTask(a2a_pb2.GetTaskRequest(id=task_id), metadata=[("x-api-key", "alice")])
            ).id == task_id
            for operation, params in (
                (stub.GetTask, a2a_pb2.GetTaskRequest(id=task_id)),
                (stub.CancelTask, a2a_pb2.CancelTaskRequest(id=task_id)),
                (
                    stub.CreateTaskPushNotificationConfig,
                    a2a_pb2.TaskPushNotificationConfig(task_id=task_id, url="https://example.com/hook"),
                ),
            ):
                with pytest.raises(grpc.aio.AioRpcError) as wrong_owner:
                    await operation(params, metadata=[("x-api-key", "bob")])
                assert wrong_owner.value.code() == grpc.StatusCode.NOT_FOUND

            with pytest.raises(grpc.aio.AioRpcError) as wrong_subscriber:
                await stub.SubscribeToTask(
                    a2a_pb2.SubscribeToTaskRequest(id=task_id), metadata=[("x-api-key", "bob")]
                ).read()
            assert wrong_subscriber.value.code() == grpc.StatusCode.NOT_FOUND

            card = await stub.GetExtendedAgentCard(
                a2a_pb2.GetExtendedAgentCardRequest(), metadata=[("x-api-key", "alice")]
            )
            assert [interface.protocol_binding for interface in card.supported_interfaces] == ["GRPC"]
    finally:
        await server.stop(grace=1)
    assert server._request_handler._push_http_client.is_closed


async def test_grpc_stop_drains_return_immediately_task():
    agent = Agent(name="Background", description="Background gRPC work")
    started = asyncio.Event()
    finished = asyncio.Event()

    @agent.skill("work", streaming=True)
    async def work():
        started.set()
        try:
            await asyncio.Event().wait()
            yield "done"
        finally:
            finished.set()

    port = _free_port()
    server = agent.build_grpc_server("127.0.0.1", port)
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            request = _send_message_request(json.dumps({"skill": "work", "params": {}}))
            request.configuration.return_immediately = True
            response = await a2a_pb2_grpc.A2AServiceStub(channel).SendMessage(request)
            assert response.task.id
            await asyncio.wait_for(started.wait(), timeout=1)
            assert not finished.is_set()
    finally:
        await server.stop(grace=0)
    assert finished.is_set()
    await server.stop(grace=0)


async def test_grpc_public_messages_but_authenticated_push_only():
    agent = Agent(name="Public", description="Public tasks")

    @agent.skill("work", streaming=True)
    async def work():
        yield "done"

    port = _free_port()
    server = agent.build_grpc_server("127.0.0.1", port)
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = a2a_pb2_grpc.A2AServiceStub(channel)
            request = _send_message_request(json.dumps({"skill": "work", "params": {}}))
            response = await stub.SendMessage(request)
            task_id = response.task.id
            assert (await stub.GetTask(a2a_pb2.GetTaskRequest(id=task_id))).id == task_id
            request.configuration.task_push_notification_config.url = "https://callback.example/hook"
            for operation, params in (
                (stub.SendMessage, request),
                (
                    stub.CreateTaskPushNotificationConfig,
                    a2a_pb2.TaskPushNotificationConfig(task_id=task_id, url="https://callback.example/hook"),
                ),
                (
                    stub.GetTaskPushNotificationConfig,
                    a2a_pb2.GetTaskPushNotificationConfigRequest(task_id=task_id, id="c"),
                ),
                (
                    stub.DeleteTaskPushNotificationConfig,
                    a2a_pb2.DeleteTaskPushNotificationConfigRequest(task_id=task_id, id="c"),
                ),
                (stub.ListTaskPushNotificationConfigs, a2a_pb2.ListTaskPushNotificationConfigsRequest(task_id=task_id)),
            ):
                with pytest.raises(grpc.aio.AioRpcError) as denied:
                    await operation(params)
                assert denied.value.code() == grpc.StatusCode.FAILED_PRECONDITION
                assert "require authentication" in denied.value.details()
            with pytest.raises(grpc.aio.AioRpcError) as denied_stream:
                await stub.SendStreamingMessage(request).read()
            assert denied_stream.value.code() == grpc.StatusCode.FAILED_PRECONDITION
    finally:
        await server.stop(grace=0)


async def test_grpc_authentication_provider_errors_are_private(caplog):
    class BrokenAuth(NoAuth):
        async def authenticate(self, request):
            raise ValueError("VERIFIER_SECRET")

    agent = Agent(name="Private", description="Broken verifier", auth=BrokenAuth())
    port = _free_port()
    server = agent.build_grpc_server("127.0.0.1", port)
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = a2a_pb2_grpc.A2AServiceStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as error:
                await stub.SendMessage(_send_message_request("hello"))
            assert error.value.code() == grpc.StatusCode.UNAUTHENTICATED
            assert "VERIFIER_SECRET" not in error.value.details() + caplog.text
    finally:
        await server.stop(grace=0)


async def test_managed_grpc_closes_on_startup_failure_and_uses_one_hook_loop():
    agent = _echo_agent()
    events, loops = [], []

    @agent.on_startup
    async def startup():
        loops.append(asyncio.get_running_loop())
        raise RuntimeError("startup failure")

    @agent.on_shutdown
    async def shutdown():
        events.append("shutdown")
        loops.append(asyncio.get_running_loop())

    server = agent.build_grpc_server("127.0.0.1", _free_port())
    with pytest.raises(RuntimeError, match="startup failure"):
        await server.start()
    await server.stop(0)
    assert events == ["shutdown"]
    assert loops[0] is loops[1]


async def test_grpc_streaming_message():
    """Streaming skill over SendStreamingMessage emits task + status updates + final text."""
    agent = Agent(name="GrpcStreamBot", description="Streaming bot over gRPC")

    @agent.skill("chat", streaming=True)
    async def chat(message: str):
        for word in message.split():
            yield word

    port = _free_port()
    server = agent.build_grpc_server("127.0.0.1", port)
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = a2a_pb2_grpc.A2AServiceStub(channel)
            request = _send_message_request(json.dumps({"skill": "chat", "params": {"message": "a b c"}}))
            events = [event async for event in stub.SendStreamingMessage(request)]

        kinds = [event.WhichOneof("payload") for event in events]
        assert kinds[0] == "task"  # first event must be the Task (SDK rule)

        streamed_text = "".join(
            event.status_update.status.message.parts[0].text
            for event in events
            if event.WhichOneof("payload") == "status_update"
            and event.status_update.status.HasField("message")
            and event.status_update.status.message.parts
        )
        assert streamed_text == "abc"

        # No `final` flag in v1.0 wire: the closed stream indicates terminality.
        # The last status update must be COMPLETED.
        status_events = [e for e in events if e.WhichOneof("payload") == "status_update"]
        assert status_events[-1].status_update.status.state == a2a_pb2.TASK_STATE_COMPLETED
    finally:
        await server.stop(grace=1)
