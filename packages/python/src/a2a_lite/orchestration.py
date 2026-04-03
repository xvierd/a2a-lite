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
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class TaskHandle:
    """A handle to a remote task, wrapping the result with task metadata."""

    task_id: str
    result: Any
    _agent_url: str

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
        return await get_remote_task(self._agent_url, self.task_id, timeout)

    async def cancel(self, timeout: float = 10.0) -> dict:
        """Request cancellation of this task on the remote agent."""
        return await cancel_remote_task(self._agent_url, self.task_id, timeout)

    async def subscribe(self, webhook_url: str, token: str | None = None, timeout: float = 10.0) -> dict:
        """Register a webhook for this task on the remote agent."""
        return await set_task_push_notification(self._agent_url, self.task_id, webhook_url, token, timeout)

    async def unsubscribe(self, timeout: float = 10.0) -> dict:
        """Remove the webhook registration for this task."""
        return await delete_task_push_notification(self._agent_url, self.task_id, timeout)

    async def get_push_config(self, timeout: float = 10.0) -> dict:
        """Get the registered webhook config for this task."""
        return await get_task_push_notification(self._agent_url, self.task_id, timeout)


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
        self._agents: dict[str, str] = dict(agents) if agents else {}
        self._cards: dict[str, AgentCardInfo] = {}

    def add(self, name: str, url: str, auto_discover: bool = False) -> None:
        """Register an agent by name.

        Args:
            name: A friendly name for the agent.
            url: The agent's base URL.
            auto_discover: If True, fetch and cache the agent card on add.
                           Must be awaited if True (use within async context via discover()).
        """
        self._agents[name] = url.rstrip("/")
        if auto_discover:
            # Schedule discovery; caller should await this in an async context
            asyncio.ensure_future(self.discover(name))

    def get(self, name: str) -> str | None:
        """Get an agent URL by name.

        Args:
            name: The agent name.

        Returns:
            The agent URL, or None if not found.
        """
        return self._agents.get(name)

    def remove(self, name: str) -> bool:
        """Remove an agent from the network.

        Args:
            name: The agent name to remove.

        Returns:
            True if the agent was removed, False if not found.
        """
        if name in self._agents:
            del self._agents[name]
            return True
        return False

    def list(self) -> dict[str, str]:
        """List all registered agents.

        Returns:
            Dict mapping agent names to their URLs.
        """
        return dict(self._agents)

    async def call(
        self,
        name: str,
        skill: str,
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
        url = self._agents.get(name)
        if url is None:
            raise KeyError(f"Agent '{name}' not found in network. Available: {list(self._agents.keys())}")
        result, task_id = await _call_remote_skill(url, skill, params, timeout)
        if return_handle:
            return TaskHandle(task_id=task_id, result=result, _agent_url=url)
        return result

    def get_card(self, name: str) -> AgentCardInfo | None:
        """Return the cached agent card for a named agent, or None if not cached.

        Args:
            name: The agent name.

        Returns:
            The cached AgentCardInfo, or None.
        """
        return self._cards.get(name)

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
        url = self._agents.get(name)
        if url is None:
            raise KeyError(f"Agent '{name}' not found in network. Available: {list(self._agents.keys())}")
        card = await discover(url, timeout)
        self._cards[name] = card
        return card

    async def stream(
        self,
        name: str,
        skill: str,
        timeout: float = 30.0,
        **params: Any,
    ) -> AsyncGenerator[str, None]:
        """Stream chunks from a named agent's skill via SSE.

        Args:
            name: The agent name (must be registered).
            skill: The skill to invoke on the remote agent.
            timeout: Request timeout in seconds.
            **params: Parameters to pass to the skill.

        Yields:
            Text chunks as they arrive from the remote agent.

        Raises:
            KeyError: If the agent name is not registered.
        """
        url = self._agents.get(name)
        if url is None:
            raise KeyError(f"Agent '{name}' not found in network. Available: {list(self._agents.keys())}")
        async for chunk in stream_remote_skill(url, skill, params, timeout):
            yield chunk

    async def broadcast(
        self,
        skill: str,
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
        tasks = {name: _call_remote_skill(url, skill, params, timeout) for name, url in self._agents.items()}

        results: dict[str, Any] = {}
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for name, raw_result in zip(tasks.keys(), gathered):
            if isinstance(raw_result, Exception):
                results[name] = {"error": str(raw_result), "type": type(raw_result).__name__}
            else:
                result, _task_id = raw_result
                results[name] = result

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
        url = self._agents.get(name)
        if url is None:
            raise KeyError(f"Agent '{name}' not found in network.")
        return await get_remote_task(url, task_id, timeout)

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
        url = self._agents.get(name)
        if url is None:
            raise KeyError(f"Agent '{name}' not found in network.")
        return await cancel_remote_task(url, task_id, timeout)

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents

    def __repr__(self) -> str:
        return f"AgentNetwork(agents={list(self._agents.keys())})"


async def _call_remote_skill(
    agent_url: str,
    skill: str,
    params: dict[str, Any],
    timeout: float = 30.0,
) -> tuple[Any, str]:
    """Call a remote A2A agent's skill and extract the result.

    Args:
        agent_url: Base URL of the remote agent.
        skill: Skill name to invoke.
        params: Parameters for the skill.
        timeout: Request timeout in seconds.

    Returns:
        A tuple of (parsed_result, task_id).
    """
    import httpx

    message = json.dumps({"skill": skill, "params": params})
    request_body = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "id": uuid4().hex,
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
                "messageId": uuid4().hex,
            }
        },
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(agent_url, json=request_body)
        response.raise_for_status()
        data = response.json()

    # Extract task_id from the A2A response: result.id
    rpc_result = data.get("result", {})
    task_id = rpc_result.get("id") if isinstance(rpc_result, dict) else None
    if not task_id:
        task_id = uuid4().hex

    return _extract_result(data), task_id


_TERMINAL_STATES = {"completed", "failed", "canceled", "rejected"}


async def stream_remote_skill(
    agent_url: str,
    skill: str,
    params: dict[str, Any],
    timeout: float = 30.0,
) -> AsyncGenerator[str, None]:
    """Stream chunks from a remote A2A agent skill via SSE.

    The remote agent must support streaming (supports_streaming=True in its card).
    Uses message/stream JSON-RPC method and consumes the SSE response.

    Args:
        agent_url: Base URL of the remote agent.
        skill: Skill name to invoke.
        params: Parameters for the skill.
        timeout: Request timeout in seconds.

    Yields:
        Text chunks as they arrive from the remote agent.

    Raises:
        RemoteAgentError: If the remote agent reports a failed state.
    """
    import httpx

    message = json.dumps({"skill": skill, "params": params})
    request_body = {
        "jsonrpc": "2.0",
        "method": "message/stream",
        "id": uuid4().hex,
        "params": {
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
                "messageId": uuid4().hex,
            }
        },
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
        async with client.stream("POST", agent_url, json=request_body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()

                # Skip empty lines, SSE comments, and event type lines
                if not line or line.startswith(":") or line.startswith("event:"):
                    continue

                if not line.startswith("data:"):
                    continue

                data_str = line[len("data:"):].strip()
                if not data_str:
                    continue

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    logger.debug("Skipping non-JSON SSE data: %s", data_str)
                    continue

                # Check for failed state
                status = data.get("status") or {}
                state = status.get("state", "")
                if state == "failed":
                    from .errors import RemoteAgentError

                    msg = status.get("message", {})
                    parts = msg.get("parts", []) if isinstance(msg, dict) else []
                    error_text = ""
                    for part in parts:
                        if part.get("kind") == "text" or part.get("type") == "text":
                            error_text = part.get("text", "")
                            break
                    raise RemoteAgentError(
                        error_text or "Remote agent task failed",
                        data,
                    )

                # Extract text from artifact parts
                artifact = data.get("artifact") or {}
                # Also check nested result.artifact pattern
                if not artifact:
                    result = data.get("result") or {}
                    artifact = result.get("artifact") or {}

                artifact_parts = artifact.get("parts", [])
                for part in artifact_parts:
                    if part.get("kind") == "text" or part.get("type") == "text":
                        text = part.get("text", "")
                        if text:
                            yield text

                # Extract text from status message parts
                if status:
                    msg = status.get("message") or {}
                    if isinstance(msg, dict):
                        msg_parts = msg.get("parts", [])
                        for part in msg_parts:
                            if part.get("kind") == "text" or part.get("type") == "text":
                                text = part.get("text", "")
                                if text:
                                    yield text

                # Stop on terminal event
                if data.get("final") is True or state in _TERMINAL_STATES:
                    return


def _extract_result(response: dict[str, Any]) -> Any:
    """Extract the skill result from an A2A JSON-RPC response.

    Args:
        response: The full JSON-RPC response dict.

    Returns:
        The parsed result value (dict, str, etc.).
    """
    if "error" in response:
        from .errors import RemoteAgentError

        error = response["error"]
        message = error if isinstance(error, str) else str(error)
        raise RemoteAgentError(message, response)

    result = response.get("result", {})
    parts = result.get("parts", [])

    for part in parts:
        if part.get("kind") == "text" or part.get("type") == "text":
            text = part.get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text

    return result


async def get_remote_task(agent_url: str, task_id: str, timeout: float = 10.0) -> dict:
    """Fetch the current status of a remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to query.
        timeout: Request timeout in seconds.

    Returns:
        The task status dict from the remote agent.
    """
    import httpx

    request_body = {
        "jsonrpc": "2.0",
        "method": "tasks/get",
        "id": uuid4().hex,
        "params": {"id": task_id},
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(agent_url, json=request_body)
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        from .errors import RemoteAgentError

        error = data["error"]
        message = error if isinstance(error, str) else str(error)
        raise RemoteAgentError(message, data)

    return data.get("result", {})


async def cancel_remote_task(agent_url: str, task_id: str, timeout: float = 10.0) -> dict:
    """Request cancellation of a remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to cancel.
        timeout: Request timeout in seconds.

    Returns:
        The cancellation response dict from the remote agent.
    """
    import httpx

    request_body = {
        "jsonrpc": "2.0",
        "method": "tasks/cancel",
        "id": uuid4().hex,
        "params": {"id": task_id},
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(agent_url, json=request_body)
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        from .errors import RemoteAgentError

        error = data["error"]
        message = error if isinstance(error, str) else str(error)
        raise RemoteAgentError(message, data)

    return data.get("result", {})


async def set_task_push_notification(
    agent_url: str,
    task_id: str,
    webhook_url: str,
    token: str | None = None,
    timeout: float = 10.0,
) -> dict:
    """Register a webhook URL for a specific remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to register the webhook for.
        webhook_url: The webhook URL to receive notifications.
        token: Optional bearer token for authenticating the webhook call.
        timeout: Request timeout in seconds.

    Returns:
        The JSON-RPC result dict from the remote agent.
    """
    import httpx

    request_body = {
        "jsonrpc": "2.0",
        "method": "tasks/pushNotification/set",
        "id": uuid4().hex,
        "params": {
            "id": task_id,
            "pushNotificationConfig": {"url": webhook_url, "token": token},
        },
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(agent_url, json=request_body)
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        from .errors import RemoteAgentError

        error = data["error"]
        message = error if isinstance(error, str) else str(error)
        raise RemoteAgentError(message, data)

    return data.get("result", {})


async def get_task_push_notification(
    agent_url: str,
    task_id: str,
    timeout: float = 10.0,
) -> dict:
    """Get the registered webhook config for a remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to query.
        timeout: Request timeout in seconds.

    Returns:
        The JSON-RPC result dict from the remote agent.
    """
    import httpx

    request_body = {
        "jsonrpc": "2.0",
        "method": "tasks/pushNotification/get",
        "id": uuid4().hex,
        "params": {"id": task_id},
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(agent_url, json=request_body)
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        from .errors import RemoteAgentError

        error = data["error"]
        message = error if isinstance(error, str) else str(error)
        raise RemoteAgentError(message, data)

    return data.get("result", {})


async def delete_task_push_notification(
    agent_url: str,
    task_id: str,
    timeout: float = 10.0,
) -> dict:
    """Remove the webhook registration for a remote task.

    Args:
        agent_url: Base URL of the remote agent.
        task_id: The task ID to remove the webhook for.
        timeout: Request timeout in seconds.

    Returns:
        The JSON-RPC result dict from the remote agent.
    """
    import httpx

    request_body = {
        "jsonrpc": "2.0",
        "method": "tasks/pushNotification/delete",
        "id": uuid4().hex,
        "params": {"id": task_id},
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(agent_url, json=request_body)
        response.raise_for_status()
        data = response.json()

    if "error" in data:
        from .errors import RemoteAgentError

        error = data["error"]
        message = error if isinstance(error, str) else str(error)
        raise RemoteAgentError(message, data)

    return data.get("result", {})


async def discover(agent_url: str, timeout: float = 10.0) -> AgentCardInfo:
    """Fetch and parse an agent's card from /.well-known/agent.json.

    Args:
        agent_url: Base URL of the remote agent.
        timeout: Request timeout in seconds.

    Returns:
        The parsed AgentCardInfo.
    """
    import httpx

    card_url = f"{agent_url.rstrip('/')}/.well-known/agent.json"

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(card_url)
        response.raise_for_status()
        data = response.json()

    capabilities = data.get("capabilities", {})
    skills_raw = data.get("skills", [])
    skills = [s if isinstance(s, dict) else {} for s in skills_raw]

    return AgentCardInfo(
        name=data.get("name", ""),
        description=data.get("description", ""),
        url=data.get("url", agent_url),
        version=data.get("version", ""),
        skills=skills,
        supports_streaming=capabilities.get("streaming", False),
        supports_push=capabilities.get("pushNotifications", False),
        raw=data,
    )
