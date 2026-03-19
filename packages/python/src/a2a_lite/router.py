"""
AgentRouter for path-based multi-agent routing.

Mounts multiple agents under a single Starlette app at different URL prefixes.
Each sub-agent retains its own executor, middleware, auth, and task store.

Example:
    from a2a_lite import Agent
    from a2a_lite.router import Router

    weather = Agent(name="WeatherAgent", description="Weather forecasts")
    hotels = Agent(name="HotelAgent", description="Hotel search")

    @weather.skill("forecast")
    async def forecast(city: str) -> str:
        return f"Sunny in {city}"

    @hotels.skill("search")
    async def search(city: str) -> list:
        return [{"name": "Grand Hotel", "city": city}]

    router = Router()
    router.mount("/weather", weather)
    router.mount("/hotels", hotels)
    router.run(port=8787)

The merged agent card is available at /.well-known/agent.json.
Individual agents remain accessible at:
  - /weather/.well-known/agent.json
  - /hotels/.well-known/agent.json
"""

from __future__ import annotations

import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from .agent import Agent


class Router:
    """
    Path-based router that mounts multiple A2A agents under a single server.

    Each agent is mounted at a URL prefix. The merged agent card combines
    skills from all sub-agents and is served at /.well-known/agent.json.

    Example:
        router = Router()
        router.mount("/weather", weather_agent)
        router.mount("/hotels", hotel_agent)
        router.run()
    """

    def __init__(self) -> None:
        self._mounts: list[tuple[str, Agent]] = []

    def mount(self, prefix: str, agent: Agent) -> None:
        """
        Mount an agent at a URL prefix.

        Args:
            prefix: URL prefix (e.g., "/weather"). Must start with "/".
            agent: The Agent instance to mount.
        """
        if not prefix.startswith("/"):
            prefix = "/" + prefix
        prefix = prefix.rstrip("/")
        self._mounts.append((prefix, agent))

    def build_merged_card(self, host: str = "localhost", port: int = 8787) -> dict:
        """
        Build a merged agent card combining all mounted agents' skills.

        Each skill ID is prefixed with the mount path to avoid collisions.

        Args:
            host: Hostname for the agent URL.
            port: Port for the agent URL.

        Returns:
            A dict representing the merged agent card.
        """
        all_skills = []
        names = []
        descriptions = []

        for prefix, agent in self._mounts:
            names.append(agent.name)
            descriptions.append(agent.description)
            for skill_def in agent._skills.values():
                all_skills.append(
                    {
                        "id": f"{prefix.lstrip('/')}/{skill_def.name}",
                        "name": skill_def.name,
                        "description": f"[{agent.name}] {skill_def.description}",
                        "tags": skill_def.tags,
                        "inputModes": ["application/json"],
                        "outputModes": ["application/json"],
                    }
                )

        return {
            "name": " + ".join(names) if names else "Router",
            "description": "; ".join(descriptions) if descriptions else "Multi-agent router",
            "version": "1.0.0",
            "url": f"http://{host}:{port}",
            "protocolVersion": "0.3.0",
            "capabilities": {
                "streaming": any(agent._has_streaming for _, agent in self._mounts),
                "pushNotifications": False,
            },
            "defaultInputModes": ["application/json"],
            "defaultOutputModes": ["application/json"],
            "skills": all_skills,
        }

    def build_app(self, host: str = "localhost", port: int = 8787):
        """
        Build a Starlette app with all agents mounted at their prefixes.

        Args:
            host: Hostname used to build the merged agent card URL.
            port: Port used to build the merged agent card URL.

        Returns:
            A configured Starlette application.
        """
        merged_card = self.build_merged_card(host, port)

        async def merged_card_handler(request: Request) -> JSONResponse:
            return JSONResponse(merged_card)

        routes = [
            Route("/.well-known/agent.json", endpoint=merged_card_handler),
        ]

        for prefix, agent in self._mounts:
            sub_app = agent._build_app(host, port)
            routes.append(Mount(prefix, app=sub_app))

        return Starlette(routes=routes)

    def run(
        self,
        host: str = "0.0.0.0",
        port: int = 8787,
        log_level: str = "info",
    ) -> None:
        """
        Start the router server.

        Args:
            host: Host to bind to.
            port: Port to listen on.
            log_level: Uvicorn log level.
        """
        display_host = "localhost" if host == "0.0.0.0" else host

        print(f"Starting A2A Lite Router on http://{display_host}:{port}")
        for prefix, agent in self._mounts:
            print(f"  {prefix} -> {agent.name} ({len(agent._skills)} skills)")

        app = self.build_app(display_host, port)
        uvicorn.run(app, host=host, port=port, log_level=log_level)
