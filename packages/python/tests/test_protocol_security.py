"""Wire-level ownership and callback protections, without external traffic."""

import asyncio
import json
import logging
import socket
from uuid import uuid4

import httpx
import pytest
from starlette.testclient import TestClient

from a2a_lite import Agent
from a2a_lite.auth import APIKeyAuth, AuthResult, CompositeAuth, NoAuth
from a2a_lite.push_notifications import ProtocolPushSender, PublicWebhookTransport, create_push_http_client


@pytest.fixture
def public_dns(monkeypatch):
    original = asyncio.BaseEventLoop.getaddrinfo

    async def resolve(self, host, port, **kwargs):
        if host == "callback.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
        if host == "private.example":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]
        return await original(self, host, port, **kwargs)

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", resolve)


def rpc(client, method, params, key="alice"):
    return client.post(
        "/",
        headers={"A2A-Version": "1.0", **({"X-API-Key": key} if key else {})},
        json={"jsonrpc": "2.0", "id": uuid4().hex, "method": method, "params": params},
    )


@pytest.fixture
def secured_client():
    agent = Agent(name="Secured", description="Owner isolation", auth=APIKeyAuth(keys=["alice", "bob"]))

    @agent.skill("work", streaming=True)
    async def work():
        yield "done"

    with TestClient(agent.get_app()) as client:
        response = rpc(
            client,
            "SendMessage",
            {
                "message": {
                    "role": "ROLE_USER",
                    "messageId": uuid4().hex,
                    "parts": [{"text": json.dumps({"skill": "work", "params": {}})}],
                }
            },
        )
        task = response.json()["result"]["task"]
        yield client, task["id"]


@pytest.mark.parametrize(
    "method",
    [
        "CreateTaskPushNotificationConfig",
        "GetTaskPushNotificationConfig",
        "DeleteTaskPushNotificationConfig",
        "GetTask",
        "CancelTask",
    ],
)
def test_all_operations_require_authentication(secured_client, method):
    client, task_id = secured_client
    response = rpc(client, method, {"taskId": task_id, "id": task_id, "url": "https://callback.example/hook"}, key=None)
    assert response.status_code == 401


@pytest.mark.parametrize(
    "method",
    [
        "CreateTaskPushNotificationConfig",
        "GetTaskPushNotificationConfig",
        "DeleteTaskPushNotificationConfig",
        "ListTaskPushNotificationConfigs",
        "GetTask",
        "CancelTask",
    ],
)
def test_other_identity_cannot_access_task(secured_client, public_dns, method):
    client, task_id = secured_client
    params = {"id": task_id} if method in ("GetTask", "CancelTask") else {"taskId": task_id, "id": task_id}
    if method == "CreateTaskPushNotificationConfig":
        params["url"] = "https://callback.example/hook"
    response = rpc(client, method, params, key="bob")
    assert response.json()["error"]["code"] == -32001


def test_push_requires_existing_task(secured_client, public_dns):
    client, _ = secured_client
    response = rpc(
        client, "CreateTaskPushNotificationConfig", {"taskId": "missing", "url": "https://callback.example/hook"}
    )
    assert response.json()["error"]["code"] == -32001


@pytest.mark.parametrize(
    "url",
    [
        "https://127.0.0.1/hook",
        "http://callback.example/hook",
        "https://100.64.0.1/hook",
        "https://169.254.169.254/latest",
        "https://[::1]/hook",
        "https://[::ffff:127.0.0.1]/hook",
        "https://private.example/hook",
        "file:///etc/passwd",
        "https://user:password@callback.example/hook",
        "https://callback.example/hook#fragment",
    ],
)
def test_unsafe_callback_rejected(secured_client, public_dns, url):
    client, task_id = secured_client
    response = rpc(client, "CreateTaskPushNotificationConfig", {"taskId": task_id, "url": url})
    assert response.json()["error"]["code"] == -32602


def test_public_callback_crud_and_config_ids(secured_client, public_dns):
    client, task_id = secured_client
    response = rpc(
        client,
        "CreateTaskPushNotificationConfig",
        {"taskId": task_id, "id": "config-1", "url": "https://callback.example/hook"},
    )
    assert response.json()["result"]["id"] == "config-1"
    response = rpc(client, "GetTaskPushNotificationConfig", {"taskId": task_id, "id": "config-1"})
    assert response.json()["result"]["url"] == "https://callback.example/hook"
    response = rpc(client, "GetTaskPushNotificationConfig", {"taskId": task_id, "id": "missing-config"})
    assert response.json()["error"]["code"] == -32001
    assert "result" in rpc(client, "DeleteTaskPushNotificationConfig", {"taskId": task_id, "id": "config-1"}).json()
    assert "error" in rpc(client, "GetTaskPushNotificationConfig", {"taskId": task_id, "id": "config-1"}).json()


def test_rest_ownership_and_error_media_type(secured_client):
    client, task_id = secured_client
    response = client.get(f"/tasks/{task_id}", headers={"A2A-Version": "1.0", "X-API-Key": "bob"})
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/a2a+json"
    assert response.json()["error"]["status"] == "NOT_FOUND"


def test_cross_user_cannot_read_existing_config_token_or_stream_task(secured_client, public_dns):
    client, task_id = secured_client
    rpc(
        client,
        "CreateTaskPushNotificationConfig",
        {
            "taskId": task_id,
            "id": "private-config",
            "url": "https://callback.example/hook",
            "token": "notification-secret",
        },
    )
    response = rpc(client, "GetTaskPushNotificationConfig", {"taskId": task_id, "id": "private-config"}, key="bob")
    assert response.json()["error"]["code"] == -32001
    assert "notification-secret" not in response.text
    for method, params in (
        ("SubscribeToTask", {"id": task_id}),
        (
            "SendStreamingMessage",
            {
                "message": {
                    "messageId": uuid4().hex,
                    "role": "ROLE_USER",
                    "taskId": task_id,
                    "parts": [{"text": "work"}],
                }
            },
        ),
    ):
        response = rpc(client, method, params, key="bob")
        assert "-32001" in response.text
    response = rpc(client, "ListTasks", {}, key="bob")
    assert not response.json()["result"].get("tasks")


@pytest.mark.parametrize("identity", [None, "", " ", 123])
def test_successful_auth_requires_a_stable_string_identity(identity):
    class InvalidIdentityAuth(NoAuth):
        async def authenticate(self, request):
            return AuthResult.success(identity)

    with TestClient(Agent(name="a", description="b", auth=InvalidIdentityAuth()).get_app()) as client:
        response = client.get("/tasks", headers={"A2A-Version": "1.0"})
        assert response.status_code == 401


def test_cors_applies_to_authentication_failures():
    agent = Agent(name="a", description="b", auth=APIKeyAuth(keys=["key"]), cors_origins=["https://client.example"])
    with TestClient(agent.get_app()) as client:
        response = client.post("/", json={}, headers={"Origin": "https://client.example"})
        assert response.status_code == 401
        assert response.headers["Access-Control-Allow-Origin"] == "https://client.example"


def test_authentication_provider_errors_are_private(caplog):
    class BrokenAuth(NoAuth):
        async def authenticate(self, request):
            raise ValueError("VERIFIER_SECRET")

    with TestClient(Agent(name="a", description="b", auth=BrokenAuth()).get_app()) as client:
        response = client.get("/tasks", headers={"A2A-Version": "1.0"})
    assert response.status_code == 401
    assert "VERIFIER_SECRET" not in response.text + caplog.text


@pytest.fixture(params=[None, CompositeAuth([APIKeyAuth(keys=["secret"]), NoAuth()])])
def public_client(request):
    agent = Agent(name="Public", description="Public tasks without dynamic callbacks", auth=request.param)

    @agent.skill("work", streaming=True)
    async def work():
        yield "done"

    with TestClient(agent.get_app()) as client:
        response = rpc(client, "SendMessage", _work_params(), key=None)
        task_id = response.json()["result"]["task"]["id"]
        assert rpc(client, "GetTask", {"id": task_id}, key=None).json()["result"]["id"] == task_id
        yield client, task_id


def _work_params():
    return {
        "message": {
            "role": "ROLE_USER",
            "messageId": uuid4().hex,
            "parts": [{"text": json.dumps({"skill": "work", "params": {}})}],
        }
    }


@pytest.mark.parametrize("binding", ["rpc", "rest"])
@pytest.mark.parametrize("operation", ["Create", "Get", "Delete", "List"])
def test_public_agent_rejects_anonymous_push_crud(public_client, binding, operation):
    client, task_id = public_client
    params = {"taskId": task_id, "id": "config-1", "url": "https://callback.example/hook"}
    if binding == "rpc":
        method = f"{operation}TaskPushNotificationConfig" + ("s" if operation == "List" else "")
        response = rpc(client, method, params, key=None)
        assert response.json()["error"]["code"] == -32004
    else:
        path = f"/tasks/{task_id}/pushNotificationConfigs"
        if operation in ("Get", "Delete"):
            path += "/config-1"
        response = client.request(
            {"Create": "POST", "Get": "GET", "Delete": "DELETE", "List": "GET"}[operation],
            path,
            headers={"A2A-Version": "1.0"},
            **({"json": params} if operation == "Create" else {}),
        )
        assert response.status_code == 400
        assert response.headers["content-type"] == "application/a2a+json"
    assert "require authentication" in response.text


@pytest.mark.parametrize("binding", ["rpc", "rest"])
@pytest.mark.parametrize("stream", [False, True])
def test_public_agent_rejects_anonymous_inline_push(public_client, binding, stream):
    client, _ = public_client
    params = _work_params()
    params["configuration"] = {"taskPushNotificationConfig": {"url": "https://callback.example/hook"}}
    if binding == "rpc":
        response = rpc(client, "SendStreamingMessage" if stream else "SendMessage", params, key=None)
    else:
        response = client.post(
            "/message:stream" if stream else "/message:send", json=params, headers={"A2A-Version": "1.0"}
        )
    assert "require authentication" in response.text


def test_authenticated_inline_push_is_accepted(secured_client, public_dns, monkeypatch):
    from a2a_lite.push_notifications import _PushHttpClient

    async def deliver(self, url, **kwargs):
        return True

    monkeypatch.setattr(_PushHttpClient, "post_callback", deliver)
    client, _ = secured_client
    params = _work_params()
    params["configuration"] = {"taskPushNotificationConfig": {"id": "inline", "url": "https://callback.example/hook"}}
    response = rpc(client, "SendMessage", params)
    task_id = response.json()["result"]["task"]["id"]
    config = rpc(client, "GetTaskPushNotificationConfig", {"taskId": task_id, "id": "inline"})
    assert config.json()["result"]["url"] == "https://callback.example/hook"


async def test_sdk_sender_uses_guarded_transport_and_protocol_payload(public_dns):
    from a2a.server.context import ServerCallContext
    from a2a.server.tasks import InMemoryPushNotificationConfigStore
    from a2a.types import AuthenticationInfo, Task, TaskPushNotificationConfig

    from a2a_lite.push_notifications import validate_callback_url

    requests = []
    client = create_push_http_client()
    client._transport._transport = httpx.MockTransport(lambda request: requests.append(request) or httpx.Response(200))
    store = InMemoryPushNotificationConfigStore()
    await store.set_info(
        "task-1",
        TaskPushNotificationConfig(
            url="https://callback.example/hook",
            token="notification-token",
            authentication=AuthenticationInfo(scheme="Bearer", credentials="callback-token"),
        ),
        ServerCallContext(),
    )
    async with client:
        sender = ProtocolPushSender(client, store, push_url_validator=validate_callback_url)
        await sender.send_notification("task-1", Task(id="task-1", context_id="context-1"))
    assert len(requests) == 1
    assert requests[0].url.host == "93.184.216.34"
    assert requests[0].headers["Authorization"] == "Bearer callback-token"
    assert requests[0].headers["X-A2A-Notification-Token"] == "notification-token"
    assert requests[0].headers["Content-Type"] == "application/a2a+json"
    assert requests[0].extensions["timeout"]["connect"] == 10.0
    assert json.loads(requests[0].content)["task"]["id"] == "task-1"


@pytest.mark.parametrize("outcome", [200, 503, "exception"])
async def test_push_logs_never_include_callback_secrets(public_dns, caplog, outcome):
    from a2a.server.context import ServerCallContext
    from a2a.server.tasks import InMemoryPushNotificationConfigStore
    from a2a.types import Task, TaskPushNotificationConfig

    from a2a_lite.push_notifications import validate_callback_url

    def deliver(request):
        if outcome == "exception":
            raise ValueError(f"{request.url} HEADER_SECRET BODY_SECRET")
        return httpx.Response(outcome, text="BODY_SECRET")

    client = create_push_http_client()
    client._transport._transport = httpx.MockTransport(deliver)
    store = InMemoryPushNotificationConfigStore()
    await store.set_info(
        "task-1",
        TaskPushNotificationConfig(url="https://callback.example/hook?token=QUERY_SECRET", token="HEADER_SECRET"),
        ServerCallContext(),
    )
    with caplog.at_level(logging.DEBUG):
        async with client:
            sender = ProtocolPushSender(client, store, push_url_validator=validate_callback_url)
            await sender.send_notification("task-1", Task(id="task-1", context_id="context-1"))
    for secret in ("QUERY_SECRET", "HEADER_SECRET", "BODY_SECRET", "callback.example"):
        assert secret not in caplog.text


async def test_push_sender_deadline_bounds_slow_headers(public_dns, monkeypatch):
    from a2a.server.tasks import InMemoryPushNotificationConfigStore
    from a2a.types import Task, TaskPushNotificationConfig

    from a2a_lite import push_notifications

    canceled = asyncio.Event()

    async def never_respond(request):
        try:
            await asyncio.Event().wait()
        finally:
            canceled.set()

    monkeypatch.setattr(push_notifications, "CALLBACK_DELIVERY_TIMEOUT", 0.01)
    client = create_push_http_client()
    client._transport._transport = httpx.MockTransport(never_respond)
    async with client:
        sender = ProtocolPushSender(client, InMemoryPushNotificationConfigStore())
        assert not await sender._dispatch_notification(
            Task(id="task-1"), TaskPushNotificationConfig(url="https://callback.example/hook"), "task-1"
        )
    assert canceled.is_set()


async def test_push_sender_closes_response_without_reading_body(public_dns):
    class UnboundedBody(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            raise AssertionError("Callback response body must not be read")
            yield b"unreachable"

        async def aclose(self):
            self.closed = True

    body = UnboundedBody()
    client = create_push_http_client()
    client._transport._transport = httpx.MockTransport(lambda request: httpx.Response(200, stream=body))
    async with client:
        assert await client.post_callback("https://callback.example/hook", json={}, headers={})
    assert body.closed


async def test_callback_transport_pins_public_address_and_preserves_tls_name(public_dns):
    requests = []

    def capture(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    client = create_push_http_client()
    transport = client._transport
    transport._transport = httpx.MockTransport(capture)
    async with client:
        delivered = await client.post_callback("https://callback.example/hook", json={"task": "test"}, headers={})
    assert not delivered
    assert len(requests) == 1
    assert requests[0].url.host == "93.184.216.34"
    assert requests[0].headers["Host"] == "callback.example"
    assert requests[0].extensions["sni_hostname"] == "callback.example"


async def test_callback_dns_rebinding_is_blocked(public_dns, monkeypatch):
    from a2a_lite.push_notifications import validate_callback_url

    assert await validate_callback_url("https://callback.example/hook")

    async def rebound(self, host, port, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", rebound)
    transport = PublicWebhookTransport()
    sent = []
    transport._transport = httpx.MockTransport(lambda request: sent.append(request) or httpx.Response(200))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.ConnectError, match="not public"):
            await client.post("https://callback.example/hook")
    assert not sent


async def test_callback_dns_timeout_fails_closed(monkeypatch):
    from a2a_lite import push_notifications

    canceled = asyncio.Event()

    async def never_resolves(self, host, port, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            canceled.set()

    monkeypatch.setattr(push_notifications, "CALLBACK_DNS_TIMEOUT", 0.01)
    monkeypatch.setattr(asyncio.BaseEventLoop, "getaddrinfo", never_resolves)
    assert not await push_notifications.validate_callback_url("https://callback.example/hook")
    assert canceled.is_set()
    canceled.clear()
    async with create_push_http_client() as client:
        with pytest.raises(httpx.ConnectTimeout, match="DNS lookup timed out"):
            await client.post("https://callback.example/hook")
    assert canceled.is_set()
