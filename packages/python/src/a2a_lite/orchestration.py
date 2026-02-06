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
from typing import Any, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


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

    def __init__(self, agents: Optional[Dict[str, str]] = None) -> None:
        self._agents: Dict[str, str] = dict(agents) if agents else {}

    def add(self, name: str, url: str) -> None:
        """Register an agent by name.

        Args:
            name: A friendly name for the agent.
            url: The agent's base URL.
        """
        self._agents[name] = url.rstrip("/")

    def get(self, name: str) -> Optional[str]:
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

    def list(self) -> Dict[str, str]:
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
        **params: Any,
    ) -> Any:
        """Call a named agent's skill and return the parsed result.

        Args:
            name: The agent name (must be registered).
            skill: The skill to invoke on the remote agent.
            timeout: Request timeout in seconds.
            **params: Parameters to pass to the skill.

        Returns:
            The parsed result from the remote agent.

        Raises:
            KeyError: If the agent name is not registered.
        """
        url = self._agents.get(name)
        if url is None:
            raise KeyError(
                f"Agent '{name}' not found in network. "
                f"Available: {list(self._agents.keys())}"
            )
        return await _call_remote_skill(url, skill, params, timeout)

    async def broadcast(
        self,
        skill: str,
        timeout: float = 30.0,
        **params: Any,
    ) -> Dict[str, Any]:
        """Call the same skill on all agents in the network concurrently.

        Args:
            skill: The skill to invoke on each agent.
            timeout: Request timeout in seconds.
            **params: Parameters to pass to the skill.

        Returns:
            Dict mapping agent names to their results (or error dicts).
        """
        tasks = {
            name: _call_remote_skill(url, skill, params, timeout)
            for name, url in self._agents.items()
        }

        results: Dict[str, Any] = {}
        gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for name, result in zip(tasks.keys(), gathered):
            if isinstance(result, Exception):
                results[name] = {"error": str(result), "type": type(result).__name__}
            else:
                results[name] = result

        return results

    def __len__(self) -> int:
        return len(self._agents)

    def __contains__(self, name: str) -> bool:
        return name in self._agents

    def __repr__(self) -> str:
        return f"AgentNetwork(agents={list(self._agents.keys())})"


async def _call_remote_skill(
    agent_url: str,
    skill: str,
    params: Dict[str, Any],
    timeout: float = 30.0,
) -> Any:
    """Call a remote A2A agent's skill and extract the result.

    Args:
        agent_url: Base URL of the remote agent.
        skill: Skill name to invoke.
        params: Parameters for the skill.
        timeout: Request timeout in seconds.

    Returns:
        The parsed result value from the remote agent.
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

    return _extract_result(data)


def _extract_result(response: Dict[str, Any]) -> Any:
    """Extract the skill result from an A2A JSON-RPC response.

    Args:
        response: The full JSON-RPC response dict.

    Returns:
        The parsed result value (dict, str, etc.).
    """
    if "error" in response:
        return response["error"]

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
