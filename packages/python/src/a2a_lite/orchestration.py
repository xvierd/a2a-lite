"""
Multi-agent orchestration for A2A Lite.

Provides AgentNetwork for managing and calling remote agents by name.

Example (simple delegate):
    weather = await agent.delegate("http://weather-agent:8787", "forecast", city="NYC")

Example (named network):
    network = AgentNetwork()
    network.add("weather", "http://weather-agent:8787")
    network.add("hotels", "http://hotel-agent:8787")
    agent = Agent(name="Planner", description="...", network=network)

    @agent.skill("plan_trip")
    async def plan_trip(destination: str):
        weather = await agent.delegate("weather", "forecast", city=destination)
        hotels = await agent.delegate("hotels", "search", city=destination)
        return {"weather": weather, "hotels": hotels}
"""

from __future__ import annotations

import asyncio
import codecs
import io
import json
import re
from collections.abc import AsyncGenerator
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import httpx

from .client import ClientConfig
from .errors import RemoteAgentError


@dataclass
class TaskHandle:
    """A handle to a remote task, wrapping the result with task metadata."""

    task_id: str
    result: Any
    _agent_url: str
    _client: ClientConfig | None = field(default=None, repr=False)
    context_id: str = ""

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("The remote agent returned a message without a task ID; task tracking is unavailable.")

    def __str__(self) -> str:
        return str(self.result)

    def __repr__(self) -> str:
        return f"TaskHandle(task_id={self.task_id!r}, result={self.result!r})"

    @property
    def agent_url(self) -> str:
        """The URL of the agent that owns this task."""
        return self._agent_url

    async def get_status(self, timeout: float = 10.0) -> dict:
        """Poll the remote agent for this task's current status."""
        return await get_remote_task(self._agent_url, self.task_id, timeout, client_config=self._client)

    async def cancel(self, timeout: float = 10.0) -> dict:
        """Request cancellation of this task on the remote agent."""
        return await cancel_remote_task(self._agent_url, self.task_id, timeout, client_config=self._client)

    def events(self, timeout: float = 30.0) -> AsyncGenerator[dict, None]:
        """Subscribe to the active task's SSE updates, starting with its current snapshot."""
        return _stream_rpc(self.agent_url, "SubscribeToTask", {"id": self.task_id}, timeout, self._client)

    async def continue_task(self, skill: str, /, timeout: float = 30.0, **params: Any) -> TaskHandle:
        """Send a follow-up skill invocation in this task and context."""
        context_id = self.context_id or (await self.get_status(timeout)).get("contextId", "")
        raw = await _call_remote_skill(
            self.agent_url,
            skill,
            params,
            timeout,
            client_config=self._client,
            task_id=self.task_id,
            context_id=context_id,
        )
        handle = _task_handle(raw, self.agent_url, self._client)
        if handle.task_id != self.task_id or (context_id and handle.context_id and handle.context_id != context_id):
            raise RemoteAgentError("Continuation returned a different task or context", raw)
        return handle

    async def subscribe(self, webhook_url: str, token: str | None = None, timeout: float = 10.0) -> dict:
        """Register a webhook for this task on the remote agent."""
        return await set_task_push_notification(
            self._agent_url, self.task_id, webhook_url, token, timeout, client_config=self._client
        )

    async def unsubscribe(self, timeout: float = 10.0) -> dict:
        """Remove the webhook registration for this task."""
        return await delete_task_push_notification(self._agent_url, self.task_id, timeout, client_config=self._client)

    async def get_push_config(self, timeout: float = 10.0) -> dict:
        """Get the registered webhook config for this task."""
        return await get_task_push_notification(self._agent_url, self.task_id, timeout, client_config=self._client)


@dataclass
class AgentCardInfo:
    """Parsed agent card information from a remote agent."""

    name: str
    description: str
    url: str
    version: str
    skills: list[dict]
    supports_streaming: bool
    supports_push: bool
    raw: dict
    tenant: str = ""
    discovery_url: str = ""

    def client_config(self, config: ClientConfig | None = None) -> ClientConfig:
        """Bind credentials to the discovery origin and tenant of this interface."""
        return (config or ClientConfig()).bind(self.discovery_url or self.url).for_interface(self.url, self.tenant)


@dataclass
class _Registration:
    base_url: str
    config: ClientConfig
    auto_discover: bool = False
    card: AgentCardInfo | None = None
    pending: asyncio.Task[AgentCardInfo] | None = None

    @property
    def endpoint(self) -> str:
        return self.card.url if self.card else self.base_url

    async def _fetch(self, timeout: float) -> AgentCardInfo:
        self.card = await discover(self.base_url, timeout, client_config=self.config)
        return self.card

    def start_discovery(self, timeout: float = 10.0) -> asyncio.Task[AgentCardInfo]:
        self.pending = asyncio.create_task(self._fetch(timeout))
        # Background failures stay available to awaiters, including the first call
        # after a failed automatic discovery. Observe them even if the peer is removed.
        self.pending.add_done_callback(lambda task: None if task.cancelled() else task.exception())
        return self.pending


class AgentNetwork:
    """Registry of named remote A2A agents.

    Provides a simple way to manage and call multiple remote agents
    by name instead of URL.

    Args:
        agents: Optional dict mapping names to URLs for initial registration.

    Example:
        network = AgentNetwork()
        network.add("weather", "http://weather-agent:8787")
        result = await network.call("weather", "forecast", city="NYC")
    """

    def __init__(self, agents: dict[str, str] | None = None) -> None:
        self._agents = {name: _Registration(url, ClientConfig().bind(url)) for name, url in (agents or {}).items()}

    def add(
        self, name: str, url: str, auto_discover: bool = False, *, client_config: ClientConfig | None = None
    ) -> None:
        """Register an agent by name.

        Args:
            name: A friendly name for the agent.
            url: The agent's base URL.
            auto_discover: Fetch the card in the running event loop, or on first use.
                All named operations await discovery before contacting the endpoint.
        """
        peer = _Registration(url.rstrip("/"), (client_config or ClientConfig()).bind(url), auto_discover)
        self._agents[name] = peer
        if auto_discover:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return
            peer.start_discovery()

    def get(self, name: str) -> str | None:
        """Get an agent URL by name.

        Args:
            name: The agent name.

        Returns:
            The agent URL, or None if not found.
        """
        peer = self._agents.get(name)
        return peer.endpoint if peer else None

    def remove(self, name: str) -> bool:
        """Remove an agent from the network.

        Args:
            name: The agent name to remove.

        Returns:
            True if the agent was removed, False if not found.
        """
        return self._agents.pop(name, None) is not None

    def list(self) -> dict[str, str]:
        """List all registered agents.

        Returns:
            Dict mapping agent names to their URLs.
        """
        return {name: peer.endpoint for name, peer in self._agents.items()}

    def _registration(self, name: str) -> _Registration:
        try:
            return self._agents[name]
        except KeyError:
            raise KeyError(f"Agent '{name}' not found in network. Available: {list(self._agents)}") from None

    async def _peer(
        self, name: str, config: ClientConfig | None = None, *, use_card: bool = True
    ) -> tuple[str, ClientConfig]:
        peer = self._registration(name)
        if peer.auto_discover and peer.card is None:
            # One canceled caller must not cancel discovery for other callers.
            await asyncio.shield(peer.pending or peer.start_discovery())
            if self._agents.get(name) is not peer:
                return await self._peer(name, config, use_card=use_card)
        base = peer.base_url
        config = (config or peer.config).bind(base)
        card = peer.card if use_card else None
        if card is None:
            return base, config
        if config.tenant and config.tenant != card.tenant:
            url, tenant = _select_jsonrpc_interface(card.raw, base, config.tenant)
            return url, config.for_interface(url, tenant)
        return card.url, card.client_config(config)

    async def call(
        self,
        name: str,
        skill: str,
        /,
        timeout: float = 30.0,
        return_handle: bool = False,
        **params: Any,
    ) -> Any:
        """Call a named agent's skill and return the parsed result.

        Args:
            name: The agent name (must be registered).
            skill: The skill to invoke on the remote agent.
            timeout: Request timeout in seconds.
            return_handle: If True, return a TaskHandle instead of just the result.
            **params: Parameters to pass to the skill.

        Returns:
            The parsed result from the remote agent, or a TaskHandle if return_handle=True.

        Raises:
            KeyError: If the agent name is not registered.
        """
        url, config = await self._peer(name)
        raw = await _call_remote_skill(url, skill, params, timeout, client_config=config)
        return _task_handle(raw, url, config) if return_handle else _extract_result(raw)

    def get_card(self, name: str) -> AgentCardInfo | None:
        """Return the cached agent card for a named agent, or None if not cached.

        Args:
            name: The agent name.

        Returns:
            The cached AgentCardInfo, or None.
        """
        peer = self._agents.get(name)
        return peer.card if peer else None

    async def discover(self, name: str, timeout: float = 10.0) -> AgentCardInfo:
        """Fetch and cache the agent card for a named agent.

        Args:
            name: The agent name (must be registered).
            timeout: Request timeout in seconds.

        Returns:
            The fetched AgentCardInfo.

        Raises:
            KeyError: If the agent name is not registered.
        """
        peer = self._registration(name)
        if peer.pending and not peer.pending.done():
            return await asyncio.shield(peer.pending)
        return await asyncio.shield(peer.start_discovery(timeout))

    async def stream(self, name: str, skill: str, /, timeout: float = 30.0, **params: Any) -> AsyncGenerator[str, None]:
        """Yield text chunks from the named skill."""
        url, config = await self._peer(name)
        async with aclosing(stream_remote_skill(url, skill, params, timeout, client_config=config)) as chunks:
            async for chunk in chunks:
                yield chunk

    async def stream_events(
        self, name: str, skill: str, /, timeout: float = 30.0, **params: Any
    ) -> AsyncGenerator[dict, None]:
        """Yield complete A2A StreamResponse objects, including non-text parts and metadata."""
        url, config = await self._peer(name)
        async with aclosing(
            _stream_rpc(url, "SendStreamingMessage", _skill_params(skill, params), timeout, config)
        ) as events:
            async for event in events:
                yield event

    async def subscribe_task(self, name: str, task_id: str, timeout: float = 30.0) -> AsyncGenerator[dict, None]:
        """Attach to a task's existing SSE stream by ID."""
        url, config = await self._peer(name)
        async with aclosing(_stream_rpc(url, "SubscribeToTask", {"id": task_id}, timeout, config)) as events:
            async for event in events:
                yield event

    async def list_tasks(
        self,
        name: str,
        *,
        page_size: int | None = None,
        page_token: str | None = None,
        context_id: str | None = None,
        status: str | None = None,
        history_length: int | None = None,
        status_timestamp_after: str | None = None,
        include_artifacts: bool | None = None,
        timeout: float = 10.0,
    ) -> dict:
        """Return one ListTasks page. Pass nextPageToken unchanged to fetch the next page."""
        url, config = await self._peer(name)
        filters = {
            "pageSize": page_size,
            "pageToken": page_token,
            "contextId": context_id,
            "status": status,
            "historyLength": history_length,
            "statusTimestampAfter": status_timestamp_after,
            "includeArtifacts": include_artifacts,
        }
        params = {key: value for key, value in filters.items() if value is not None}
        return (await _rpc_request(url, "ListTasks", params, timeout, client_config=config))["result"]

    async def continue_task(
        self, name: str, task_id: str, skill: str, /, timeout: float = 30.0, *, context_id: str = "", **params: Any
    ) -> TaskHandle:
        """Continue an existing task by ID. Fetch its context when only the task ID is known."""
        url, config = await self._peer(name)
        return await TaskHandle(task_id, None, url, config, context_id).continue_task(skill, timeout, **params)

    async def broadcast(
        self,
        skill: str,
        /,
        timeout: float = 30.0,
        **params: Any,
    ) -> dict[str, Any]:
        """Call the same skill on all agents in the network concurrently.

        Args:
            skill: The skill to invoke on each agent.
            timeout: Request timeout in seconds.
            **params: Parameters to pass to the skill.

        Returns:
            Dict mapping agent names to their results (or error dicts).
        """

        async def invoke(name: str) -> Any:
            url, config = await self._peer(name)
            raw = await _call_remote_skill(url, skill, params, timeout, client_config=config)
            return _extract_result(raw)

        names = list(self._agents)
        gathered = await asyncio.gather(*(invoke(name) for name in names), return_exceptions=True)
        results: dict[str, Any] = {}
        for name, value in zip(names, gathered):
            results[name] = (
                {"error": str(value), "type": type(value).__name__} if isinstance(value, Exception) else value
            )
        return results

    async def get_task(self, name: str, task_id: str, timeout: float = 10.0) -> dict:
        """Fetch the current status of a task running on a named agent.

        Args:
            name: The agent name (must be registered).
            task_id: The task ID to query.
            timeout: Request timeout in seconds.

        Returns:
            The task status dict from the remote agent.

        Raises:
            KeyError: If the agent name is not registered.
        """
        url, config = await self._peer(name)
        return await get_remote_task(url, task_id, timeout, client_config=config)

    async def cancel_task(self, name: str, task_id: str, timeout: float = 10.0) -> dict:
        """Request cancellation of a task running on a named agent.

        Args:
            name: The agent name (must be registered).
            task_id: The task ID to cancel.
            timeout: Request timeout in seconds.

        Returns:
            The cancellation response dict from the remote agent.

        Raises:
            KeyError: If the agent name is not registered.
        """
        url, config = await self._peer(name)
        return await cancel_remote_task(url, task_id, timeout, client_config=config)

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents

    def __repr__(self) -> str:
        return f"AgentNetwork(agents={list(self._agents.keys())})"


def _message_params(text: str, task_id: str = "", context_id: str = "") -> dict:
    message = {"role": "ROLE_USER", "messageId": uuid4().hex, "parts": [{"text": text}]}
    if task_id:
        message["taskId"] = task_id
    if context_id:
        message["contextId"] = context_id
    return {"message": message}


def _skill_params(skill: str, params: dict, task_id: str = "", context_id: str = "") -> dict:
    return _message_params(json.dumps({"skill": skill, "params": params}), task_id, context_id)


def _rpc_body(method: str, params: dict, config: ClientConfig) -> dict:
    return {"jsonrpc": "2.0", "method": method, "id": uuid4().hex, "params": config.request_params(params)}


def _check_envelope(data: Any, request_id: str) -> dict:
    if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
        raise RemoteAgentError("Invalid JSON-RPC response version", data if isinstance(data, dict) else None)
    if data.get("id") != request_id:
        raise RemoteAgentError("JSON-RPC response ID does not match the request", data)
    if ("result" in data) == ("error" in data):
        raise RemoteAgentError("JSON-RPC response must contain exactly one of result and error", data)
    if "error" in data:
        error = data["error"]
        if (
            not isinstance(error, dict)
            or type(error.get("code")) is not int
            or not isinstance(error.get("message"), str)
        ):
            raise RemoteAgentError("Invalid JSON-RPC error object", data)
        raise RemoteAgentError(error["message"], data, code=error["code"], data=error.get("data"))
    return data


def _http_envelope(response: httpx.Response, request_id: str) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        response.raise_for_status()
        raise RemoteAgentError("Invalid JSON in JSON-RPC response") from exc
    # An HTTP error may carry a correlated JSON-RPC error with application details.
    if isinstance(data, dict) and "error" in data and "jsonrpc" in data:
        _check_envelope(data, request_id)
    response.raise_for_status()
    return _check_envelope(data, request_id)


async def _rpc_request(
    agent_url: str,
    method: str,
    params: dict,
    timeout: float,
    *,
    client_config: ClientConfig | None = None,
    headers: dict[str, str] | None = None,
) -> dict:
    config = (client_config or ClientConfig()).bind(agent_url)
    body = _rpc_body(method, params, config)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.post(agent_url, json=body, headers=await config.request_headers(agent_url, headers))
        return _http_envelope(response, body["id"])


async def _call_remote_skill(
    agent_url: str,
    skill: str,
    params: dict[str, Any],
    timeout: float = 30.0,
    *,
    client_config: ClientConfig | None = None,
    task_id: str = "",
    context_id: str = "",
) -> dict:
    body = _skill_params(skill, params, task_id, context_id)
    response = await _rpc_request(agent_url, "SendMessage", body, timeout, client_config=client_config)
    return response["result"]


def _task_handle(result: dict, url: str, config: ClientConfig | None) -> TaskHandle:
    task = result.get("task") or {}
    message = result.get("message") or {}
    task_id = task.get("id") or message.get("taskId") or result.get("id", "")
    context_id = task.get("contextId") or message.get("contextId") or result.get("contextId", "")
    return TaskHandle(task_id, _extract_result(result), url, config, context_id)


_TERMINAL_STATES = {
    "TASK_STATE_COMPLETED",
    "TASK_STATE_FAILED",
    "TASK_STATE_CANCELED",
    "TASK_STATE_REJECTED",
}
_INTERRUPTED_STATES = {"TASK_STATE_INPUT_REQUIRED", "TASK_STATE_AUTH_REQUIRED"}
_STREAM_VARIANTS = {"task", "message", "artifactUpdate", "statusUpdate"}


def _event_status(event: dict) -> dict:
    return (event.get("statusUpdate") or event.get("task") or {}).get("status", {})


async def _sse_lines(response: httpx.Response) -> AsyncGenerator[str, None]:
    # Only CR, LF and CRLF delimit SSE lines. Python's incremental newline
    # decoder handles split CRLF and UTF-8 sequences without splitting U+2028.
    decoder = io.IncrementalNewlineDecoder(codecs.getincrementaldecoder("utf-8-sig")(), translate=True)
    partial: list[str] = []
    try:
        async for chunk in response.aiter_bytes():
            *lines, tail = decoder.decode(chunk).split("\n")
            if lines:
                lines[0] = "".join(partial) + lines[0]
                partial.clear()
                for line in lines:
                    yield line
            if tail:
                partial.append(tail)
        # A final CR still terminates a line. A partial data line also needs to
        # reach the event parser so it can distinguish truncation from clean EOF.
        if decoder.decode(b"", final=True) or partial:
            yield "".join(partial)
    except UnicodeDecodeError as exc:
        raise RemoteAgentError("Invalid UTF-8 in SSE stream") from exc


async def _sse_events(response: httpx.Response) -> AsyncGenerator[tuple[str, str], None]:
    event = ""
    data: list[str] = []
    async with aclosing(_sse_lines(response)) as lines:
        async for line in lines:
            if not line:
                if data or event == "error":
                    yield event, "\n".join(data)
                event = ""
                data = []
                continue
            field, _, value = line.partition(":")
            if field == "data":
                data.append(value.removeprefix(" "))
            elif field == "event":
                event = value.removeprefix(" ")
    if data or event == "error":
        raise RemoteAgentError("Truncated SSE event at end of stream")


async def _stream_rpc(
    url: str,
    method: str,
    params: dict,
    timeout: float,
    client_config: ClientConfig | None,
    *,
    text_stream: bool = False,
) -> AsyncGenerator[dict, None]:
    config = (client_config or ClientConfig()).bind(url)
    body = _rpc_body(method, params, config)
    headers = httpx.Headers(await config.request_headers(url))
    headers["Accept"] = "text/event-stream, application/json"
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        async with client.stream("POST", url, json=body, headers=headers) as response:
            mime = response.headers.get("content-type", "").partition(";")[0].strip().lower()
            if not response.is_success or mime != "text/event-stream":
                await response.aread()
                _http_envelope(response, body["id"])
                raise RemoteAgentError(f"{method} expected a text/event-stream response")

            interrupted = False
            subscribed_id = params["id"] if method == "SubscribeToTask" else None
            seen_snapshot = False
            async with aclosing(_sse_events(response)) as events:
                async for event_name, payload in events:
                    if not payload and event_name != "error":
                        continue
                    try:
                        data = json.loads(payload)
                    except ValueError as exc:
                        raise RemoteAgentError("Invalid JSON in SSE event") from exc
                    event = _check_envelope(data, body["id"])["result"]
                    if event_name == "error":
                        raise RemoteAgentError("SSE error event lacks a JSON-RPC error", data)
                    variants = (
                        [event[key] for key in _STREAM_VARIANTS if key in event] if isinstance(event, dict) else []
                    )
                    if len(variants) != 1 or not isinstance(variants[0], dict):
                        raise RemoteAgentError("Invalid A2A StreamResponse", data)
                    if subscribed_id is not None:
                        if "task" in event:
                            event_id = event["task"].get("id")
                            seen_snapshot = True
                        else:
                            if not seen_snapshot:
                                raise RemoteAgentError("SubscribeToTask must start with a Task snapshot", data)
                            event_id = (event.get("statusUpdate") or event.get("artifactUpdate") or {}).get("taskId")
                        if event_id != subscribed_id:
                            raise RemoteAgentError("Subscription event does not match the requested task ID", data)
                    status = _event_status(event)
                    state = status.get("state")
                    if state:
                        interrupted = state in _INTERRUPTED_STATES
                    if text_stream and state == "TASK_STATE_FAILED":
                        parts = (status.get("message") or {}).get("parts", [])
                        reason = next((p["text"] for p in parts if p.get("text")), "Remote agent task failed")
                        raise RemoteAgentError(reason, data)
                    yield event
                    if "message" in event or state in _TERMINAL_STATES:
                        return
            if not interrupted:
                raise RemoteAgentError("SSE stream ended before a final message or task state")


async def stream_remote_skill(
    agent_url: str,
    skill: str,
    params: dict[str, Any],
    timeout: float = 30.0,
    *,
    client_config: ClientConfig | None = None,
) -> AsyncGenerator[str, None]:
    """Yield text from A2A artifact, status and message events. Surface failures in stream order."""
    events = _stream_rpc(
        agent_url, "SendStreamingMessage", _skill_params(skill, params), timeout, client_config, text_stream=True
    )
    async with aclosing(events):
        async for event in events:
            status = _event_status(event)
            message = status.get("message") or event.get("message") or {}
            artifact = event.get("artifactUpdate", {}).get("artifact", {})
            for item in (artifact, message):
                for part in item.get("parts", []):
                    if part.get("text"):
                        yield part["text"]


def _extract_result(result: Any) -> Any:
    """Extract the Lite convenience value from a validated SendMessage result."""
    # A2A v1.0: result.message.parts (Message) or result.task.status.message.parts (Task)
    candidates: list[dict] = []
    if isinstance(result, dict):
        if isinstance(result.get("message"), dict):
            candidates.append(result["message"])
        if isinstance(result.get("task"), dict):
            task = result["task"]
            candidates.extend(task.get("artifacts", []))
            status = task.get("status") or {}
            if isinstance(status.get("message"), dict):
                candidates.append(status["message"])
        # Tolerate a bare result with parts (legacy shape)
        if "parts" in result:
            candidates.append(result)

    for candidate in candidates:
        for part in candidate.get("parts", []):
            if "text" in part:
                text = part.get("text", "")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text

    return result


async def get_remote_task(
    agent_url: str,
    task_id: str,
    timeout: float = 10.0,
    *,
    headers: dict[str, str] | None = None,
    client_config: ClientConfig | None = None,
) -> dict:
    """Fetch the current status of a remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to query.
        timeout: Request timeout in seconds.
        headers: Authentication headers for the remote agent (not the callback).

    Returns:
        The task status dict from the remote agent.
    """
    return (
        await _rpc_request(agent_url, "GetTask", {"id": task_id}, timeout, client_config=client_config, headers=headers)
    )["result"]


async def cancel_remote_task(
    agent_url: str,
    task_id: str,
    timeout: float = 10.0,
    *,
    headers: dict[str, str] | None = None,
    client_config: ClientConfig | None = None,
) -> dict:
    """Request cancellation of a remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to cancel.
        timeout: Request timeout in seconds.
        headers: Authentication headers for the remote agent (not the callback).

    Returns:
        The cancellation response dict from the remote agent.
    """
    return (
        await _rpc_request(
            agent_url, "CancelTask", {"id": task_id}, timeout, client_config=client_config, headers=headers
        )
    )["result"]


async def set_task_push_notification(
    agent_url: str,
    task_id: str,
    webhook_url: str,
    token: str | None = None,
    timeout: float = 10.0,
    *,
    headers: dict[str, str] | None = None,
    client_config: ClientConfig | None = None,
) -> dict:
    """Register a webhook URL for a specific remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to register the webhook for.
        webhook_url: The webhook URL to receive notifications.
        token: Optional bearer token for authenticating the webhook call.
        timeout: Request timeout in seconds.
        headers: Authentication headers for the remote agent (not the callback).

    Returns:
        The JSON-RPC result dict from the remote agent.
    """
    params = {"taskId": task_id, "id": task_id, "url": webhook_url, "token": token}
    if token:
        params["authentication"] = {"scheme": "Bearer", "credentials": token}
    return (
        await _rpc_request(
            agent_url, "CreateTaskPushNotificationConfig", params, timeout, client_config=client_config, headers=headers
        )
    )["result"]


async def get_task_push_notification(
    agent_url: str,
    task_id: str,
    timeout: float = 10.0,
    *,
    headers: dict[str, str] | None = None,
    client_config: ClientConfig | None = None,
) -> dict:
    """Get the registered webhook config for a remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to query.
        timeout: Request timeout in seconds.
        headers: Authentication headers for the remote agent (not the callback).

    Returns:
        The JSON-RPC result dict from the remote agent.
    """
    return (
        await _rpc_request(
            agent_url,
            "GetTaskPushNotificationConfig",
            {"id": task_id, "taskId": task_id},
            timeout,
            client_config=client_config,
            headers=headers,
        )
    )["result"]


async def delete_task_push_notification(
    agent_url: str,
    task_id: str,
    timeout: float = 10.0,
    *,
    headers: dict[str, str] | None = None,
    client_config: ClientConfig | None = None,
) -> dict:
    """Remove the webhook registration for a remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to remove the webhook for.
        timeout: Request timeout in seconds.
        headers: Authentication headers for the remote agent (not the callback).

    Returns:
        The JSON-RPC result dict from the remote agent.
    """
    return (
        await _rpc_request(
            agent_url,
            "DeleteTaskPushNotificationConfig",
            {"id": task_id, "taskId": task_id},
            timeout,
            client_config=client_config,
            headers=headers,
        )
    )["result"]


async def discover(
    agent_url: str, timeout: float = 10.0, *, client_config: ClientConfig | None = None
) -> AgentCardInfo:
    """Fetch and parse an agent's card from /.well-known/agent-card.json.

    Args:
        agent_url: Base URL of the remote agent.
        timeout: Request timeout in seconds.

    Returns:
        The parsed AgentCardInfo.

    Raises:
        RemoteAgentError: If the remote agent speaks A2A 0.3 (unsupported).
    """
    card_url = f"{agent_url.rstrip('/')}/.well-known/agent-card.json"

    config = (client_config or ClientConfig()).bind(agent_url)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        response = await client.get(card_url, headers=await config.request_headers(card_url))
        response.raise_for_status()
        data = response.json()

    # Detect A2A 0.3 cards (root `url` + `protocolVersion`, no supportedInterfaces)
    if "supportedInterfaces" not in data and ("url" in data or "protocolVersion" in data):
        raise RemoteAgentError(
            f"Agent at {agent_url} speaks A2A 0.3, not supported by a2a-lite 1.0",
            data,
        )

    interface_url, tenant = _select_jsonrpc_interface(data, agent_url, config.tenant)
    config.check_endpoint(interface_url)

    capabilities = data.get("capabilities", {})
    skills_raw = data.get("skills", [])
    skills = [s if isinstance(s, dict) else {} for s in skills_raw]

    return AgentCardInfo(
        name=data.get("name", ""),
        description=data.get("description", ""),
        url=interface_url,
        version=data.get("version", ""),
        skills=skills,
        supports_streaming=capabilities.get("streaming", False),
        supports_push=capabilities.get("pushNotifications", False),
        raw=data,
        tenant=tenant,
        discovery_url=agent_url,
    )


def _select_jsonrpc_interface(card: dict, base: str, tenant: str) -> tuple[str, str]:
    """Choose an advertised compatible endpoint, honoring an explicitly requested tenant."""
    unscoped = None
    for interface in card.get("supportedInterfaces", []):
        if not isinstance(interface, dict) or interface.get("protocolBinding") != "JSONRPC":
            continue
        if not re.fullmatch(r"1\.0(?:\.\d+)?", str(interface.get("protocolVersion", ""))):
            continue
        url = interface.get("url", "")
        if not isinstance(url, str) or urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).hostname:
            continue
        advertised = interface.get("tenant", "")
        if not isinstance(advertised, str):
            continue
        if not tenant or advertised == tenant:
            return url, advertised
        if not advertised and unscoped is None:
            unscoped = url
    if unscoped:
        return unscoped, ""
    raise RemoteAgentError(
        f"Agent at {base} has no supported A2A 1.0 JSON-RPC interface for the requested tenant", card
    )
