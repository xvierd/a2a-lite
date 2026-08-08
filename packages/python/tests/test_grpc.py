"""Tests for the EXPERIMENTAL gRPC transport (agent.run_grpc / build_grpc_server).

Skipped entirely when the optional grpc extra is not installed:
pip install a2a-lite[grpc]
"""

import json
import socket

import pytest

from a2a_lite import Agent

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
