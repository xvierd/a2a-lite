"""Credentials follow trusted endpoints and stay attached to task handles."""

import json

import httpx
import pytest

from a2a_lite import Agent, AgentNetwork, ClientConfig
from a2a_lite.auth import APIKeyAuth
from a2a_lite.orchestration import discover


async def test_provider_refresh_and_task_handle_context(monkeypatch):
    agent = Agent(
        name="Remote",
        description="Credential refresh",
        auth=APIKeyAuth(principals={"old": "same-user", "new": "same-user"}, authorized_tenants={"tenant-a"}),
    )

    @agent.skill("work", task=True)
    async def work():
        return "done"

    app = agent.get_app()
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.ASGITransport(app=app), **kw))
    calls = []

    async def credentials(url):
        calls.append(url)
        return {"X-API-Key": "old" if len(calls) == 1 else "new"}

    config = ClientConfig(credential_provider=credentials, tenant="tenant-a")
    network = AgentNetwork()
    network.add("remote", "http://localhost:8787", client_config=config)
    handle = await network.call("remote", "work", return_handle=True)
    assert handle.result == "done"
    assert (await handle.get_status())["id"] == handle.task_id
    assert len(calls) == 2
    assert "old" not in repr(handle) + repr(config)
    assert (await network.discover("remote")).name == "Remote"


@pytest.mark.parametrize("allowed", [False, True])
async def test_discovery_rejects_untrusted_origin_before_provider_forwarding(monkeypatch, allowed):
    calls = []
    requests = []
    card = {
        "name": "remote",
        "supportedInterfaces": [
            {"url": "https://different.example/rpc", "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}
        ],
    }

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=card)

    def credentials(url):
        calls.append(url)
        return {"Authorization": "Bearer PRIVATE"}

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    config = ClientConfig(
        credential_provider=credentials,
        allowed_origins=frozenset({"https://different.example"}) if allowed else frozenset(),
    )
    if allowed:
        assert (await discover("https://original.example", client_config=config)).url == "https://different.example/rpc"
    else:
        with pytest.raises(ValueError, match="untrusted origin"):
            await discover("https://original.example", client_config=config)
    assert calls == ["https://original.example/.well-known/agent-card.json"]
    assert len(requests) == 1


async def test_discovery_does_not_follow_redirect_or_forward_credentials(monkeypatch):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://untrusted.example/card"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    with pytest.raises(httpx.HTTPStatusError):
        await discover(
            "https://original.example", client_config=ClientConfig(headers={"Authorization": "Bearer PRIVATE"})
        )
    assert len(requests) == 1


async def test_stream_and_push_helpers_keep_headers_and_tenant(monkeypatch):
    from a2a_lite.orchestration import TaskHandle, stream_remote_skill

    requests = []

    def respond(request):
        body = json.loads(request.content)
        requests.append((request.headers, body))
        if body["method"] == "SendStreamingMessage":
            return httpx.Response(
                200,
                headers={"Content-Type": "text/event-stream"},
                text='data: {"result":{"message":{"parts":[{"text":"chunk"}]}}}\n\n',
            )
        return httpx.Response(200, json={"result": {"id": "task-1"}})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(respond), **kw))
    config = ClientConfig(headers={"X-API-Key": "PRIVATE"}, tenant="tenant-a").bind("https://remote.example")
    assert [
        chunk async for chunk in stream_remote_skill("https://remote.example", "work", {}, client_config=config)
    ] == ["chunk"]
    handle = TaskHandle("task-1", "result", "https://remote.example", config)
    await handle.subscribe("https://callback.example")
    await handle.get_push_config()
    await handle.unsubscribe()
    await handle.cancel()
    assert len(requests) == 5
    assert all(
        headers["X-API-Key"] == "PRIVATE" and body["params"]["tenant"] == "tenant-a" for headers, body in requests
    )
