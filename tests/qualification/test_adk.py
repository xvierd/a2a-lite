"""Google ADK consuming A2A/1.0 over JSON-RPC, with one fresh session per test."""

import asyncio
import json
import os
from importlib.metadata import version

# These tests use only a remote A2A agent and an in-memory session service.
os.environ["OTEL_SDK_DISABLED"] = "true"

import httpx
import pytest
from a2a.client import ClientConfig, ClientFactory
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from artifact_peer import artifact_peer
from run import TOKEN

CARD = "/.well-known/agent-card.json"
PLAIN = "Hola, ¿me puedes saludar?"
MODES = pytest.mark.parametrize(
    "legacy", (True, False), ids=("legacy", "new-integration")
)


@pytest.fixture(scope="module", autouse=True)
def check_versions(record_testsuite_property):
    for package, expected in [("google-adk", "2.15.0"), ("a2a-sdk", "1.3.1")]:
        actual = version(package)
        record_testsuite_property(package, actual)
        assert actual == expected, f"{package} {actual}, expected {expected}"
    record_testsuite_property("adkBinding", "JSONRPC")


def skill(name, **params):
    return json.dumps({"skill": name, "params": params})


def texts(events):
    return [
        part.text
        for event in events
        if event.content
        for part in event.content.parts
        if part.text is not None
    ]


def response(event):
    return (event.custom_metadata or {}).get("a2a:response", {})


async def run_turn(url, legacy, text, streaming, observe_extension=None):
    """Observe actual transport/method and obtain both the live events and session history."""
    calls = []
    origin = httpx.URL(url)

    async def before_request(request):
        assert (request.url.scheme, request.url.host, request.url.port) == (
            origin.scheme,
            origin.host,
            origin.port,
        )
        if request.method == "GET":
            calls.append(request.url.path)
        else:
            calls.append(json.loads(request.content)["method"])
            if observe_extension:
                observe_extension(request.headers.get("A2A-Extensions", "(absent)"))

    async with httpx.AsyncClient(
        headers={"X-API-Key": TOKEN, "A2A-Version": "1.0"},
        timeout=10,
        trust_env=False,
        event_hooks={"request": [before_request]},
    ) as http:
        factory = ClientFactory(
            ClientConfig(
                httpx_client=http,
                streaming=streaming,
                supported_protocol_bindings=["JSONRPC"],
            )
        )
        agent = RemoteA2aAgent(
            "peer", url + CARD, a2a_client_factory=factory, use_legacy=legacy
        )
        runner = InMemoryRunner(agent=agent, app_name="qualification")
        ids = {"app_name": "qualification", "user_id": "local"}
        try:
            session = await runner.session_service.create_session(**ids)
            message = types.Content(role="user", parts=[types.Part(text=text)])
            async with asyncio.timeout(20):
                live = [
                    ev
                    async for ev in runner.run_async(
                        user_id="local", session_id=session.id, new_message=message
                    )
                ]
            saved = await runner.session_service.get_session(
                **ids, session_id=session.id
            )
            assert saved is not None
            assert calls == [
                CARD,
                "SendStreamingMessage" if streaming else "SendMessage",
            ]
            assert texts(ev for ev in saved.events if ev.author == "user") == [text]
            return live, [ev for ev in saved.events if ev.author == agent.name]
        finally:
            await runner.close()


def assert_message(events, expected):
    assert all(not event.error_code and not event.error_message for event in events)
    assert texts(events) == [expected]
    (message,) = [response(event) for event in events if event.content]
    assert message["role"] == "ROLE_AGENT" and message["messageId"]
    assert message["parts"] == [{"text": expected}]


@MODES
def test_unary_message(peer, language, legacy, record_testsuite_property):
    def observe_extension(value):
        record_testsuite_property(
            f"{language}.use_legacy={legacy}.A2A-Extensions", value
        )

    for events in asyncio.run(
        run_turn(peer, legacy, skill("greet", text="saludo"), False, observe_extension)
    ):
        assert_message(events, "saludo")


@MODES
def test_stream(peer, legacy):
    for events in asyncio.run(run_turn(peer, legacy, skill("stream"), True)):
        assert not any(event.error_code or event.error_message for event in events)
        assert texts(events) == ["one", "two", "three"]
        assert response(events[-1])["status"]["state"] == "TASK_STATE_COMPLETED"


def assert_failure(events):
    assert response(events[-1]).get("status", {}).get("state") == "TASK_STATE_FAILED"
    assert events[-1].error_code == "A2A_TASK_FAILED"
    assert events[-1].error_message
    return events[-1].error_message


@MODES
@pytest.mark.parametrize("streaming", (False, True), ids=("unary", "stream"))
def test_failed_task(peer, legacy, streaming):
    for events in asyncio.run(run_turn(peer, legacy, skill("fail"), streaming)):
        assert_failure(events)


def test_ambiguous_text(peer, language):
    for events in asyncio.run(run_turn(peer, False, PLAIN, True)):
        if language == "java":
            diagnostic = assert_failure(events)
            expected_type = "SkillNotFoundException"
        else:
            # These runtimes preserve selection diagnostics as an ordinary Message.
            (diagnostic,) = texts(events)
            assert_message(events, diagnostic)
            expected_type = "SkillNotFoundError"
        detail = json.loads(diagnostic)
        assert detail["type"] == expected_type
        assert "Unknown skill" in detail["error"]
        assert {"greet", "stream", "fail"} <= set(detail["available_skills"])


@pytest.mark.parametrize(
    "text,expected",
    [(PLAIN, PLAIN), (skill("greet", text="explicit"), "explicit")],
    ids=("plain", "skill"),
)
def test_configured_text_entry(text_peer, text, expected):
    for events in asyncio.run(run_turn(text_peer, False, text, False)):
        assert_message(events, expected)


@MODES
def test_fragmented_artifact_without_last_chunk(legacy):
    with artifact_peer() as url:
        live, saved = asyncio.run(run_turn(url, legacy, "send pieces", True))
    assert texts(ev for ev in live if ev.partial) == ["first ", "second"]
    for events in (live, saved):
        assert not any(ev.error_code or ev.error_message for ev in events)
        (final,) = [ev for ev in events if not ev.partial and texts([ev])]
        assert "".join(texts([final])) == "first second"
        assert response(events[-1])["status"]["state"] == "TASK_STATE_COMPLETED"
    assert not any(ev.partial for ev in saved)
