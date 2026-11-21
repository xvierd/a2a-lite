"""Public Lite client contracts at the HTTP boundary."""

import asyncio
import json
from contextlib import aclosing

import httpx
import pytest

from a2a_lite import Agent, AgentNetwork, ClientConfig, TaskContext
from a2a_lite.errors import RemoteAgentError

RPC_URL = "https://peer.example/v1/rpc"
ERROR = {"code": -32001, "message": "Task missing", "data": {"taskId": "absent"}}
SNAPSHOT = {"task": {"id": "a", "contextId": "c", "status": {"state": "TASK_STATE_WORKING"}}}
COMPLETE = {"statusUpdate": {"taskId": "a", "contextId": "c", "status": {"state": "TASK_STATE_COMPLETED"}}}


def frame(envelope):
    return b"data: " + json.dumps(envelope, ensure_ascii=False).encode() + b"\n\n"


class ByteStream(httpx.AsyncByteStream):
    """Split both UTF-8 sequences and CRLF boundaries, and track response closure."""

    def __init__(self, body):
        self.body = body
        self.closed = False

    async def __aiter__(self):
        for offset in range(len(self.body)):
            yield self.body[offset : offset + 1]

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize("line_ending", [b"\n", b"\r", b"\r\n"], ids=["lf", "cr", "crlf"])
async def test_multiline_fragmented_sse_preserves_parts_and_metadata(mock_http, line_ending):
    artifact = {
        "artifactUpdate": {
            "taskId": "a",
            "contextId": "c",
            "artifact": {"artifactId": "x", "parts": [{"text": "mañana\u2028🍊"}, {"data": {"answer": 42}}]},
            "metadata": {"source": "peer"},
        }
    }
    task = {"task": {"id": "a", "contextId": "c", "status": {"state": "TASK_STATE_WORKING"}}}
    streams = []

    def respond(request):
        header = {"jsonrpc": "2.0", "id": json.loads(request.content)["id"]}
        body = b": heartbeat\n\n" + frame({**header, "result": task})
        body += b"event: message\n"
        # SSE joins consecutive data fields with a newline. Split the JSON between tokens.
        body += frame({**header, "result": artifact}).replace(b', "result"', b',\ndata: "result"')
        body += frame({**header, "result": COMPLETE})
        stream = ByteStream(body.replace(b"\n", line_ending))
        streams.append(stream)
        return httpx.Response(200, headers={"Content-Type": "Text/Event-Stream; charset=UTF-8"}, stream=stream)

    mock_http(respond)
    network = AgentNetwork({"peer": RPC_URL})
    assert [event async for event in network.stream_events("peer", "work")] == [task, artifact, COMPLETE]
    assert [text async for text in network.stream("peer", "work")] == ["mañana\u2028🍊"]
    assert all(stream.closed for stream in streams)


@pytest.mark.parametrize("mode", ["json-before-stream", "sse-before-chunk", "sse-after-chunk"])
async def test_stream_rpc_error_keeps_code_and_data_and_closes_response(mock_http, mode):
    streams = []

    def respond(request):
        header = {"jsonrpc": "2.0", "id": json.loads(request.content)["id"]}
        if mode == "json-before-stream":
            raw = json.dumps({**header, "error": ERROR}).encode()
            mime = "application/json; charset=utf-8"
        else:
            raw = frame({**header, "error": ERROR})
            mime = "text/event-stream"
            if mode == "sse-after-chunk":
                raw = frame({**header, "result": {"artifactUpdate": {"artifact": {"parts": [{"text": "once"}]}}}}) + raw
        stream = ByteStream(raw)
        streams.append(stream)
        return httpx.Response(200, headers={"Content-Type": mime}, stream=stream)

    mock_http(respond)
    network = AgentNetwork({"peer": RPC_URL})
    texts = []
    with pytest.raises(RemoteAgentError, match="Task missing") as caught:
        async for text in network.stream("peer", "work"):
            texts.append(text)
    assert caught.value.code == ERROR["code"]
    assert caught.value.data == ERROR["data"]
    assert texts == (["once"] if mode == "sse-after-chunk" else [])
    assert streams[0].closed


@pytest.mark.parametrize("operation", ["message", "task", "stream"])
@pytest.mark.parametrize("defect", ["wrong-version", "wrong-id", "missing-id", "no-outcome", "two-outcomes"])
async def test_invalid_envelope_never_becomes_a_result(mock_http, defect, operation):
    def respond(request):
        envelope = {"jsonrpc": "2.0", "id": json.loads(request.content)["id"], "result": COMPLETE}
        if defect == "wrong-version":
            envelope["jsonrpc"] = "1.0"
        elif defect == "wrong-id":
            envelope["id"] = "another-request"
        elif defect == "missing-id":
            del envelope["id"]
        elif defect == "no-outcome":
            del envelope["result"]
        else:
            envelope["error"] = ERROR
        if operation == "stream":
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=frame(envelope))
        return httpx.Response(200, json=envelope)

    mock_http(respond)
    network = AgentNetwork({"peer": RPC_URL})
    with pytest.raises(RemoteAgentError) as caught:
        if operation == "stream":
            await anext(network.stream_events("peer", "work"))
        elif operation == "task":
            await network.get_task("peer", "a")
        else:
            await network.call("peer", "work")
    if defect == "two-outcomes":
        assert str(caught.value) != ERROR["message"]


@pytest.mark.parametrize("ended_mid_frame", [False, True])
async def test_eof_before_terminal_event_raises(mock_http, ended_mid_frame):
    def respond(request):
        header = {"jsonrpc": "2.0", "id": json.loads(request.content)["id"]}
        event = {"artifactUpdate": {"artifact": {"parts": [{"text": "partial"}]}}}
        body = frame({**header, "result": event})
        if ended_mid_frame:
            body += frame({**header, "result": COMPLETE}).rstrip(b"\n")
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=body)

    mock_http(respond)
    stream = AgentNetwork({"peer": RPC_URL}).stream("peer", "work")
    assert await anext(stream) == "partial"
    with pytest.raises(RemoteAgentError):
        await anext(stream)


@pytest.mark.parametrize("subscribe", [False, True], ids=["send-stream", "subscribe-task"])
async def test_aclose_releases_underlying_response_immediately(mock_http, subscribe):
    streams = []

    def respond(request):
        header = {"jsonrpc": "2.0", "id": json.loads(request.content)["id"]}
        event = SNAPSHOT if subscribe else {"artifactUpdate": {"artifact": {"parts": [{"text": "a"}]}}}
        stream = ByteStream(frame({**header, "result": event}) + frame({**header, "result": COMPLETE}))
        streams.append(stream)
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=stream)

    mock_http(respond)
    network = AgentNetwork({"peer": RPC_URL})
    events = network.subscribe_task("peer", "a") if subscribe else network.stream("peer", "work")
    async with aclosing(events):
        await anext(events)
        assert not streams[0].closed
    assert streams[0].closed


async def test_structured_stream_keeps_failed_snapshot_and_final_message(sse_reply):
    failed = {"task": {"id": "a", "contextId": "c", "status": {"state": "TASK_STATE_FAILED"}}}
    message = {"message": {"messageId": "m", "role": "ROLE_AGENT", "parts": [{"text": "done"}], "metadata": {"n": 1}}}
    network = AgentNetwork({"peer": RPC_URL})
    for result in (failed, message):
        sse_reply([{"result": result}])
        assert [event async for event in network.stream_events("peer", "work")] == [result]


@pytest.mark.parametrize("continues", [False, True])
async def test_subscription_can_close_or_continue_after_input_required(sse_reply, continues):
    waiting = {"task": {"id": "a", "status": {"state": "TASK_STATE_INPUT_REQUIRED"}}}
    events = [waiting, COMPLETE] if continues else [waiting]
    sse_reply([{"result": event} for event in events])
    network = AgentNetwork({"peer": RPC_URL})
    assert [event async for event in network.subscribe_task("peer", "a")] == events


async def test_tenant_endpoint_and_credentials_follow_each_handle(mock_http):
    network = AgentNetwork()
    task = {"id": "t1", "contextId": "c", "status": {"state": "TASK_STATE_INPUT_REQUIRED"}}
    counters = {}

    def provider(name):
        async def credentials(url):
            await asyncio.sleep(0)
            counters[name] = counters.get(name, 0) + 1
            return {"Authorization": f"Bearer {name}-{counters[name]}"}

        return credentials

    def respond(request):
        name = request.url.path.split("/")[1]
        assert name in ("north", "south")
        assert request.headers["Authorization"].startswith(f"Bearer {name}-")
        assert request.headers["A2A-Version"] == "1.0"
        if request.method == "GET":
            assert request.url.path == f"/{name}/.well-known/agent-card.json"
            return httpx.Response(
                200,
                json={
                    "skills": [{"id": "work"}],
                    "supportedInterfaces": [
                        {
                            "url": "https://peer.example/rest",
                            "protocolBinding": "HTTP+JSON",
                            "protocolVersion": "1.0",
                            "tenant": "rest",
                        },
                        {
                            "url": "https://peer.example/old",
                            "protocolBinding": "JSONRPC",
                            "protocolVersion": "0.3",
                            "tenant": "old",
                        },
                        {
                            "url": f"https://peer.example/{name}/rpc",
                            "protocolBinding": "JSONRPC",
                            "protocolVersion": "1.0",
                            "tenant": name,
                        },
                    ],
                },
            )
        assert request.url.path == f"/{name}/rpc"
        body = json.loads(request.content)
        header = {"jsonrpc": "2.0", "id": body["id"]}
        params = body["params"]
        assert params["tenant"] == name
        method = body["method"]
        if method == "SendMessage":
            msg = params["message"]
            skill_call = json.loads(msg["parts"][0]["text"])
            expected = {"answer": "yes"} if "taskId" in msg else {}
            assert skill_call == {"skill": "work", "params": expected}
            if expected:
                assert (msg["taskId"], msg["contextId"]) == ("t1", "c")
            result = {"task": task}
        elif method == "SubscribeToTask":
            assert params["id"] == "t1"
            done = {"task": {**task, "status": {"state": "TASK_STATE_COMPLETED"}}}
            return httpx.Response(
                200, headers={"Content-Type": "text/event-stream"}, content=frame({**header, "result": done})
            )
        elif method == "ListTasks":
            assert params["pageSize"] == 1
            if "pageToken" not in params:
                result = {"tasks": [task], "nextPageToken": "opaque/+=="}
            else:
                assert params["pageToken"] == "opaque/+=="
                result = {"tasks": [{**task, "id": "t2"}]}
        else:
            assert method in {
                "GetTask",
                "CancelTask",
                "CreateTaskPushNotificationConfig",
                "GetTaskPushNotificationConfig",
                "DeleteTaskPushNotificationConfig",
            }
            assert params["id"] == "t1"
            result = task
        return httpx.Response(200, json={**header, "result": result})

    requests = mock_http(respond)

    async def use_tenant(name):
        config = ClientConfig(credential_provider=provider(name), tenant="south" if name == "south" else "")
        network.add(name, f"https://peer.example/{name}", client_config=config)
        card = await network.discover(name)
        assert card.tenant == name
        assert card.url == f"https://peer.example/{name}/rpc"
        handle = await network.call(name, "work", return_handle=True)
        await Agent("Caller", "test", network=network).delegate(name, "work", discover=True)
        assert (await handle.get_status())["id"] == handle.task_id
        events = [event async for event in handle.events()]
        assert events[0]["task"]["id"] == handle.task_id
        assert (await handle.continue_task("work", answer="yes")).task_id == handle.task_id
        assert (await network.continue_task(name, handle.task_id, "work", answer="yes")).task_id == handle.task_id
        p1 = await network.list_tasks(name, page_size=1)
        p2 = await network.list_tasks(name, page_size=1, page_token=p1["nextPageToken"])
        assert [t["id"] for t in p1["tasks"] + p2["tasks"]] == ["t1", "t2"]
        await handle.subscribe("https://receiver.example")
        await handle.get_push_config()
        await handle.unsubscribe()
        await handle.cancel()

    await asyncio.gather(use_tenant("north"), use_tenant("south"))
    assert len({request.headers["Authorization"] for request in requests}) == len(requests)


async def test_continue_input_required_task_by_id_and_by_handle(monkeypatch):
    agent = Agent("Peer", "Continuation")

    @agent.skill("review", task=True)
    async def review(task: TaskContext, answer: str = ""):
        if answer:
            return answer
        await task.update("input-required", "Which file?")
        return None

    app = agent.get_app()
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **opts: client(transport=httpx.ASGITransport(app=app), **opts))
    network = AgentNetwork({"peer": "http://peer"})
    async with app.router.lifespan_context(app):
        by_id = await network.call("peer", "review", return_handle=True)
        by_handle = await network.call("peer", "review", return_handle=True)
        results = [
            await network.continue_task("peer", by_id.task_id, "review", answer="first"),
            await by_handle.continue_task("review", answer="second"),
        ]
        assert [h.task_id for h in results] == [by_id.task_id, by_handle.task_id]
        assert [h.result for h in results] == ["first", "second"]
        for handle in results:
            assert (await handle.get_status())["status"]["state"] == "TASK_STATE_COMPLETED"
        first_page = await network.list_tasks("peer", page_size=1)
        second_page = await network.list_tasks("peer", page_size=1, page_token=first_page["nextPageToken"])
        assert [len(p["tasks"]) for p in (first_page, second_page)] == [1, 1]
        assert {p["tasks"][0]["id"] for p in (first_page, second_page)} == {by_id.task_id, by_handle.task_id}


async def test_concurrent_per_call_tenants_select_matching_interfaces(mock_http):
    card = {
        "skills": [{"id": "work"}],
        "supportedInterfaces": [
            {
                "url": f"https://peer.example/{tenant or 'shared'}",
                "protocolBinding": "JSONRPC",
                "protocolVersion": "1.0",
                "tenant": tenant,
            }
            for tenant in ("", "red", "blue")
        ],
    }

    def respond(request):
        if request.method == "GET":
            assert request.url.path == "/.well-known/agent-card.json"
            return httpx.Response(200, json=card)
        body = json.loads(request.content)
        tenant = request.headers["X-Account"]
        if tenant in ("red", "blue"):
            assert request.url.path == f"/{tenant}"
            assert body["params"]["tenant"] == tenant
        else:
            assert request.url.path == "/shared"
            assert "tenant" not in body["params"]
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"message": {"parts": [{"text": tenant}]}}}
        )

    mock_http(respond)
    network = AgentNetwork({"peer": "https://peer.example"})
    await network.discover("peer")
    caller = Agent("Caller", "testing", network=network)

    async def invoke(tenant):
        async def headers(url):
            await asyncio.sleep(0)
            return {"X-Account": tenant}

        return await caller.delegate(
            "peer", "work", client_config=ClientConfig(credential_provider=headers, tenant=tenant)
        )

    assert await asyncio.gather(*(invoke(tenant) for tenant in ("red", "blue", "green"))) == ["red", "blue", "green"]


async def test_unscoped_discovery_omits_configured_tenant_for_calls_and_handles(mock_http):
    task = {"id": "t1", "contextId": "ctx", "status": {"state": "TASK_STATE_INPUT_REQUIRED"}}
    snapshot = {"task": {**task, "status": {"state": "TASK_STATE_COMPLETED"}}}
    card = {
        "skills": [{"id": "work"}],
        "supportedInterfaces": [{"url": RPC_URL, "protocolBinding": "JSONRPC", "protocolVersion": "1.0"}],
    }

    def respond(request):
        if request.method == "GET":
            return httpx.Response(200, json=card)
        assert str(request.url) == RPC_URL
        body = json.loads(request.content)
        header = {"jsonrpc": "2.0", "id": body["id"]}
        assert "tenant" not in body["params"]
        if body["method"] in {"SendStreamingMessage", "SubscribeToTask"}:
            event = snapshot if body["method"] == "SubscribeToTask" else COMPLETE
            return httpx.Response(
                200, headers={"Content-Type": "text/event-stream"}, content=frame({**header, "result": event})
            )
        result = {"task": task} if body["method"] == "SendMessage" else task
        return httpx.Response(200, json={**header, "result": result})

    requests = mock_http(respond)
    network = AgentNetwork()
    caller = Agent("Caller", "tenant selection", network=network)

    async def use(name):
        network.add(name, "https://peer.example", client_config=ClientConfig(tenant=name, headers={"X-Account": name}))
        assert (await network.discover(name)).tenant == ""
        handle = await network.call(name, "work", return_handle=True)
        await caller.delegate(name, "work", discover=True)
        await handle.continue_task("work", answer="ok")
        await handle.get_status()
        await handle.cancel()
        await handle.subscribe("https://receiver.example")
        await handle.get_push_config()
        await handle.unsubscribe()
        await network.list_tasks(name)
        assert [e async for e in handle.events()] == [snapshot]
        assert [e async for e in network.stream_events(name, "work")] == [COMPLETE]

    await asyncio.gather(use("north"), use("south"))
    assert {r.headers["X-Account"] for r in requests} == {"north", "south"}


async def test_discovery_rejects_conflicting_tenant_before_post(mock_http):
    card = {
        "skills": [{"id": "work"}],
        "supportedInterfaces": [
            {"url": RPC_URL, "protocolBinding": "JSONRPC", "protocolVersion": "1.0", "tenant": "red"}
        ],
    }
    requests = mock_http(lambda request: httpx.Response(200, json=card))
    caller = Agent("Caller", "testing")
    with pytest.raises((RemoteAgentError, ValueError)):
        await caller.delegate("https://peer.example", "work", discover=True, client_config=ClientConfig(tenant="blue"))
    assert [r.method for r in requests] == ["GET"]


async def test_subscribe_to_in_progress_task_observes_final_status(monkeypatch):
    agent = Agent("Peer", "In-flight subscription")
    first_snapshot = asyncio.get_running_loop().create_future()
    subscribed = asyncio.Event()

    @agent.skill("work", task=True)
    async def work():
        await asyncio.wait_for(subscribed.wait(), timeout=5)
        return "finished"

    app = agent.get_app()

    async def observe_snapshot(scope, receive, send):
        async def send_response(message):
            await send(message)
            if message["type"] != "http.response.body":
                return
            for line in message.get("body", b"").splitlines():
                if line.startswith(b"data:"):
                    # ASGITransport buffers response bodies. Observe the first snapshot on
                    # the wire so the second client can attach while the skill is running.
                    result = json.loads(line[5:])["result"]
                    if "task" in result:
                        if b"x-test-subscriber" in dict(scope["headers"]):
                            subscribed.set()
                        elif not first_snapshot.done():
                            first_snapshot.set_result(result["task"]["id"])

        await app(scope, receive, send_response)

    client = httpx.AsyncClient
    transport = httpx.ASGITransport(app=observe_snapshot)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **options: client(transport=transport, **options))
    network = AgentNetwork({"peer": "http://peer"})
    network.add("subscriber", "http://peer", client_config=ClientConfig(headers={"X-Test-Subscriber": "true"}))

    async def collect(stream):
        return [event async for event in stream]

    async with app.router.lifespan_context(app):
        original = asyncio.create_task(collect(network.stream_events("peer", "work")))
        try:
            task_id = await asyncio.wait_for(first_snapshot, timeout=5)
            events = await asyncio.wait_for(collect(network.subscribe_task("subscriber", task_id)), timeout=5)
        finally:
            subscribed.set()
            sent = await original

    assert sent[0]["task"]["id"] == events[0]["task"]["id"] == task_id
    assert events[-1]["statusUpdate"]["status"]["state"] == "TASK_STATE_COMPLETED"
    assert [
        part["text"]
        for event in events
        if "artifactUpdate" in event
        for part in event["artifactUpdate"]["artifact"]["parts"]
    ] == ["finished"]


@pytest.mark.parametrize(
    "initial",
    [COMPLETE, {"message": {"taskId": "a", "parts": [{"text": "done"}]}}, {"task": {**SNAPSHOT["task"], "id": "b"}}],
    ids=["status-without-snapshot", "message-instead-of-snapshot", "wrong-snapshot-id"],
)
async def test_subscription_requires_snapshot_of_requested_task(sse_reply, initial):
    sse_reply([{"result": initial}])
    network = AgentNetwork({"peer": RPC_URL})
    with pytest.raises(RemoteAgentError):
        await anext(network.subscribe_task("peer", "a"))


@pytest.mark.parametrize(
    ("kind", "id_field"), [("task", "id"), ("statusUpdate", "taskId"), ("artifactUpdate", "taskId")]
)
@pytest.mark.parametrize("other_id", ["b", None], ids=["wrong-id", "missing-id"])
async def test_subscription_rejects_events_without_matching_task_id(sse_reply, kind, id_field, other_id):
    variants = {
        "task": SNAPSHOT["task"],
        "statusUpdate": COMPLETE["statusUpdate"],
        "artifactUpdate": {"taskId": "a", "contextId": "c", "artifact": {"artifactId": "x", "parts": [{"text": "ok"}]}},
    }
    payload = dict(variants[kind])
    if other_id is None:
        del payload[id_field]
    else:
        payload[id_field] = other_id
    sse_reply([{"result": SNAPSHOT}, {"result": {kind: payload}}, {"result": COMPLETE}])
    network = AgentNetwork({"peer": RPC_URL})
    async with aclosing(network.subscribe_task("peer", "a")) as subscription:
        assert await anext(subscription) == SNAPSHOT
        with pytest.raises(RemoteAgentError):
            await anext(subscription)


async def test_subscription_rejects_message_after_snapshot(sse_reply):
    message = {"message": {"taskId": "a", "role": "ROLE_AGENT", "parts": [{"text": "done"}]}}
    sse_reply([{"result": SNAPSHOT}, {"result": message}])
    network = AgentNetwork({"peer": RPC_URL})
    async with aclosing(network.subscribe_task("peer", "a")) as subscription:
        assert await anext(subscription) == SNAPSHOT
        with pytest.raises(RemoteAgentError):
            await anext(subscription)


async def test_subscription_surfaces_rpc_error_before_first_snapshot(sse_reply):
    sse_reply([{"error": ERROR}])
    network = AgentNetwork({"peer": RPC_URL})
    with pytest.raises(RemoteAgentError, match=ERROR["message"]) as caught:
        await anext(network.subscribe_task("peer", "a"))
    assert caught.value.code == ERROR["code"]
    assert caught.value.data == ERROR["data"]


def card_for(url, tenant):
    return {
        "skills": [{"id": "work"}],
        "supportedInterfaces": [{"url": url, "protocolBinding": "JSONRPC", "protocolVersion": "1.0", "tenant": tenant}],
    }


@pytest.mark.parametrize("operation", ["call", "delegate", "stream"])
async def test_auto_discovery_waits_before_sending(mock_http, operation):
    start_get, release_get = asyncio.Event(), asyncio.Event()

    async def respond(request):
        if request.method == "GET":
            start_get.set()
            await release_get.wait()
            return httpx.Response(200, json=card_for(RPC_URL, "red"))
        assert str(request.url) == RPC_URL
        body = json.loads(request.content)
        assert body["params"]["tenant"] == "red"
        envelope = {"jsonrpc": "2.0", "id": body["id"], "result": {"message": {"parts": [{"text": "ok"}]}}}
        if operation == "stream":
            return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, content=frame(envelope))
        return httpx.Response(200, json=envelope)

    requests = mock_http(respond)
    network = AgentNetwork()
    network.add("peer", "https://peer.example", auto_discover=True)

    async def invoke():
        if operation == "call":
            return await network.call("peer", "work")
        if operation == "delegate":
            return await Agent("Caller", "testing", network=network).delegate("peer", "work")
        return "".join([text async for text in network.stream("peer", "work")])

    invocation = asyncio.create_task(invoke())
    try:
        await asyncio.wait_for(start_get.wait(), timeout=2)
        await asyncio.sleep(0)
        assert [r.method for r in requests] == ["GET"]
    finally:
        release_get.set()
        outcome = await asyncio.wait_for(invocation, timeout=2)
    assert outcome == "ok"
    assert [r.method for r in requests] == ["GET", "POST"]


async def test_failed_auto_discovery_stops_before_post(mock_http):
    requests = mock_http(lambda request: httpx.Response(503))
    network = AgentNetwork()
    network.add("peer", "https://peer.example", auto_discover=True)
    with pytest.raises(httpx.HTTPStatusError) as caught:
        await network.call("peer", "work")
    assert caught.value.response.status_code == 503
    assert [r.method for r in requests] == ["GET"]


async def test_stale_auto_discovery_cannot_overwrite_new_registration(mock_http):
    started, release, returned = asyncio.Event(), asyncio.Event(), asyncio.Event()
    new_url = "https://peer.example/new/rpc"

    async def respond(request):
        if request.url.path == "/old/.well-known/agent-card.json":
            started.set()
            try:
                await release.wait()
                return httpx.Response(200, json=card_for("https://peer.example/old/rpc", "old"))
            finally:
                returned.set()
        if request.method == "GET":
            assert request.url.path == "/new/.well-known/agent-card.json"
            return httpx.Response(200, json=card_for(new_url, "new"))
        assert str(request.url) == new_url
        body = json.loads(request.content)
        assert body["params"]["tenant"] == "new"
        return httpx.Response(
            200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"message": {"parts": [{"text": "new"}]}}}
        )

    mock_http(respond)
    network = AgentNetwork()
    network.add("peer", "https://peer.example/old", auto_discover=True)
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        network.add("peer", "https://peer.example/new")
        assert (await network.discover("peer")).url == new_url
    finally:
        release.set()
        await asyncio.wait_for(returned.wait(), timeout=2)
    assert await network.call("peer", "work") == "new"
    assert network.get_card("peer").url == new_url


@pytest.mark.parametrize("view", ["events", "text"])
@pytest.mark.parametrize("tail", ["clean-eof", "partial-json", "missing-blank-line"])
async def test_eof_after_interrupted_task_preserves_framing_errors(mock_http, view, tail):
    waiting = {
        "task": {
            "id": "a",
            "contextId": "c",
            "status": {"state": "TASK_STATE_INPUT_REQUIRED", "message": {"parts": [{"text": "Answer?"}]}},
        }
    }

    def respond(request):
        header = {"jsonrpc": "2.0", "id": json.loads(request.content)["id"]}
        body = frame({**header, "result": waiting})
        if tail == "partial-json":
            body += b'data: {"jsonrpc":'
        elif tail == "missing-blank-line":
            body += frame({**header, "result": COMPLETE})[:-1]
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=ByteStream(body))

    mock_http(respond)
    network = AgentNetwork({"peer": RPC_URL})
    stream = network.stream_events("peer", "work") if view == "events" else network.stream("peer", "work")
    async with aclosing(stream):
        assert await anext(stream) == (waiting if view == "events" else "Answer?")
        if tail == "clean-eof":
            with pytest.raises(StopAsyncIteration):
                await anext(stream)
        else:
            with pytest.raises(RemoteAgentError):
                await anext(stream)
