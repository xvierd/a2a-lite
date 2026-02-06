"""
Testing utilities for A2A Lite agents.

Makes testing agents as simple as:

    from a2a_lite.testing import AgentTestClient

    def test_my_agent():
        client = AgentTestClient(agent)
        result = client.call("greet", name="World")
        assert result == "Hello, World!"
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict
from uuid import uuid4


@dataclass
class TestResult:
    """
    Structured result from a test client call.

    Provides multiple ways to access the result:
    - .data — parsed Python object (dict, list, int, str, etc.)
    - .text — raw text string
    - .json() — parse text as JSON (raises on invalid JSON)
    - .raw_response — the full A2A response dict
    """

    _data: Any
    _text: str
    raw_response: Dict[str, Any]

    @property
    def data(self) -> Any:
        """The parsed result value."""
        return self._data

    @property
    def text(self) -> str:
        """The raw text representation."""
        return self._text

    def json(self) -> Any:
        """Parse the text as JSON."""
        return json.loads(self._text)

    def __eq__(self, other: Any) -> bool:
        """Allow direct comparison with the data value for convenience."""
        if isinstance(other, TestResult):
            return self._data == other._data
        return self._data == other

    def __repr__(self) -> str:
        return f"TestResult(data={self._data!r})"


class AgentTestClient:
    """
    Simple test client for A2A Lite agents.

    Example:
        agent = Agent(name="Test", description="Test")

        @agent.skill("add")
        async def add(a: int, b: int) -> int:
            return a + b

        # In your test
        client = AgentTestClient(agent)
        assert client.call("add", a=2, b=3) == 5
    """

    def __init__(self, agent):
        """
        Create a test client for an agent.

        Args:
            agent: The A2A Lite Agent instance to test
        """
        self.agent = agent
        self._app = None
        self._client = None

    def _get_client(self):
        """Lazily create the test client."""
        if self._client is None:
            from starlette.testclient import TestClient as StarletteTestClient

            self._app = self.agent.get_app()
            self._client = StarletteTestClient(self._app)
        return self._client

    def call(self, skill: str, **params) -> Any:
        """
        Call a skill and return the result.

        Args:
            skill: Name of the skill to call
            **params: Parameters to pass to the skill

        Returns:
            The skill's return value (parsed from JSON if possible)

        Example:
            result = client.call("greet", name="World")
        """
        client = self._get_client()

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

        response = client.post("/", json=request_body)
        response.raise_for_status()
        data = response.json()

        # Extract the actual result from A2A response
        return self._extract_result(data)

    def _extract_result(self, response: Dict) -> TestResult:
        """Extract the skill result from A2A response."""
        if "error" in response:
            raise TestClientError(response["error"])

        result = response.get("result", {})

        # Get text from message parts
        parts = result.get("parts", [])
        for part in parts:
            if part.get("kind") == "text" or part.get("type") == "text":
                text = part.get("text", "")
                # Try to parse as JSON
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = text
                return TestResult(_data=data, _text=text, raw_response=response)

        return TestResult(_data=result, _text=json.dumps(result), raw_response=response)

    def get_agent_card(self) -> Dict[str, Any]:
        """
        Fetch the agent card.

        Returns:
            The agent card as a dictionary
        """
        client = self._get_client()
        response = client.get("/.well-known/agent.json")
        response.raise_for_status()
        return response.json()

    def list_skills(self) -> list[str]:
        """
        Get list of available skill names.

        Returns:
            List of skill names
        """
        card = self.get_agent_card()
        return [s.get("name", s.get("id")) for s in card.get("skills", [])]

    def stream(self, skill: str, **params) -> list[Any]:
        """
        Call a streaming skill and collect all results.

        Args:
            skill: Name of the skill to call
            **params: Parameters to pass to the skill

        Returns:
            List of all streamed values

        Example:
            results = client.stream("count", limit=3)
            assert len(results) == 3
        """
        import asyncio

        # Access skills directly from agent
        skill_def = self.agent._skills.get(skill)

        if not skill_def:
            raise TestClientError(f"Unknown skill: {skill}")

        # Call handler directly and collect results
        results = []

        async def run_handler():
            handler = skill_def.handler
            gen = handler(**params)

            # Handle both async and sync generators
            if hasattr(gen, "__anext__"):
                async for value in gen:
                    results.append(value)
            elif hasattr(gen, "__next__"):
                for value in gen:
                    results.append(value)
            else:
                # Not a generator, just a coroutine
                result = await gen
                results.append(result)

        # Handle both sync and async calling contexts
        try:
            asyncio.get_running_loop()
            # Already in an async context — run in a separate thread
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(1) as pool:
                pool.submit(asyncio.run, run_handler()).result()
        except RuntimeError:
            # No running loop — safe to use asyncio.run()
            asyncio.run(run_handler())
        return results


class TestClientError(Exception):
    """Error from test client."""

    pass


# Async version for async tests
class AsyncAgentTestClient:
    """
    Async test client for A2A Lite agents.

    Example:
        async def test_my_agent():
            client = AsyncAgentTestClient(agent)
            result = await client.call("greet", name="World")
            assert result == "Hello, World!"
    """

    def __init__(self, agent):
        self.agent = agent
        self._app = None
        self._client = None

    async def _get_client(self):
        """Lazily create the async test client."""
        if self._client is None:
            import httpx

            self._app = self.agent.get_app()
            self._client = httpx.AsyncClient(
                app=self._app, base_url="http://testserver"
            )
        return self._client

    async def call(self, skill: str, **params) -> Any:
        """
        Call a skill and return the result.

        Args:
            skill: Name of the skill to call
            **params: Parameters to pass to the skill

        Returns:
            The skill's return value
        """
        client = await self._get_client()

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

        response = await client.post("/", json=request_body)
        response.raise_for_status()
        data = response.json()

        return self._extract_result(data)

    def _extract_result(self, response: Dict) -> TestResult:
        """Extract the skill result from A2A response."""
        if "error" in response:
            raise TestClientError(response["error"])

        result = response.get("result", {})
        parts = result.get("parts", [])

        for part in parts:
            if part.get("kind") == "text" or part.get("type") == "text":
                text = part.get("text", "")
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    data = text
                return TestResult(_data=data, _text=text, raw_response=response)

        return TestResult(_data=result, _text=json.dumps(result), raw_response=response)

    async def close(self):
        """Close the client."""
        if self._client:
            await self._client.aclose()
            self._client = None
