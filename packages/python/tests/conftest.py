"""HTTP peers for exercising the real JSON-RPC and event-stream clients."""

import json

import httpx
import pytest


@pytest.fixture
def mock_http(monkeypatch):
    client = httpx.AsyncClient

    def install(handler):
        requests = []

        def respond(request):
            requests.append(request)
            return handler(request)

        transport = httpx.MockTransport(respond)
        monkeypatch.setattr(httpx, "AsyncClient", lambda **options: client(transport=transport, **options))
        return requests

    return install


@pytest.fixture
def rpc_reply(mock_http):
    def install(**payload):
        def respond(request):
            envelope = {"jsonrpc": "2.0", "id": json.loads(request.content)["id"], **payload}
            return httpx.Response(200, json=envelope)

        return mock_http(respond)

    return install


@pytest.fixture
def sse_reply(mock_http):
    def install(events, prefix=""):
        def respond(request):
            request_id = json.loads(request.content)["id"]
            frames = ["data: " + json.dumps({"jsonrpc": "2.0", "id": request_id, **event}) + "\n\n" for event in events]
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=prefix + "".join(frames))

        return mock_http(respond)

    return install
