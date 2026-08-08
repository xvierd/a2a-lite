"""
BattleshipAgent - a Battleship player exposed as an A2A agent with a2a-lite.

Every game message travels over the real A2A protocol (JSON-RPC SendMessage,
wire v1.0, header `A2A-Version: 1.0`, lite convention: the text part is a
JSON payload `{"skill": ..., "params": {...}}`).

Skills:
    new_game()                        -> reset with a fresh random fleet
    receive_shot(row, col)            -> opponent fires at THIS agent's board
    next_shot()                       -> pick this agent's next firing coordinate
    report_shot_result(row, col, ...) -> feedback for this agent's strategy
    status()                          -> ships remaining / shot counters

State lives in process memory (one game per agent instance) — fine for a
demo; no task_store needed.

Config via env vars (so two instances can run side by side):
    BATTLESHIP_NAME       agent display name     (default "Capitán A2A")
    BATTLESHIP_STRATEGY   "hunter" | "random"    (default "hunter")
    BATTLESHIP_PORT       listen port            (default 8790)

The same server also serves the web UI (static/index.html) on GET /.
`agent.run()` cannot add extra routes, so __main__ builds the app with
`get_app()` and wraps it in a tiny ASGI layer that serves the HTML on GET,
then calls `uvicorn.run()` manually. All A2A traffic is untouched.
"""

from __future__ import annotations

import os
import random
from pathlib import Path

from a2a_lite import Agent

from game import Board
from strategy import make_strategy

STATIC_DIR = Path(__file__).parent / "static"


class BattleshipAgent:
    """A Battleship player: board + strategy, exposed through A2A skills."""

    def __init__(
        self,
        name: str = "Capitán A2A",
        strategy: str = "hunter",
        seed: int | None = None,
        url: str | None = None,
    ):
        self.name = name
        self.strategy_name = strategy
        self._rng = random.Random(seed)
        self._strategy = make_strategy(strategy, self._rng)
        self.board = Board(self._rng)
        self.my_shots = 0

        self.agent = Agent(
            name=name,
            description=f"Battleship player ({strategy} strategy) speaking A2A v1.0",
            version="1.0.0",
            url=url,
        )
        self._register_skills()

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------
    def _register_skills(self) -> None:
        agent = self.agent

        @agent.skill("new_game")
        async def new_game() -> dict:
            """Reset the board with a fresh random fleet and clear strategy memory."""
            self.board = Board(self._rng)
            self._strategy = make_strategy(self.strategy_name, self._rng)
            self.my_shots = 0
            return {"ok": True, "ships": len(self.board.ships)}

        @agent.skill("receive_shot")
        async def receive_shot(row: int, col: int) -> dict:
            """An opponent shot hits THIS agent's board at (row, col)."""
            return self.board.receive_shot(row, col)

        @agent.skill("next_shot")
        async def next_shot() -> dict:
            """Pick this agent's next firing coordinate using its strategy."""
            r, c = self._strategy.next_shot()
            return {"row": r, "col": c}

        @agent.skill("report_shot_result")
        async def report_shot_result(row: int, col: int, result: str, ship: str = "") -> dict:
            """The referee (arena/UI) reports the outcome of this agent's shot."""
            self.my_shots += 1
            self._strategy.record_result(row, col, result, ship or None)
            return {"ok": True}

        @agent.skill("status")
        async def status() -> dict:
            """Current game status for this agent."""
            return {
                "name": self.name,
                "strategy": self.strategy_name,
                "ships_remaining": self.board.ships_remaining,
                "shots_received": len(self.board.shots_received),
                "my_shots": self.my_shots,
            }

    def get_app(self):
        """The plain A2A ASGI app (JSON-RPC + agent card, no UI)."""
        return self.agent.get_app()


def with_ui(app, static_dir: Path = STATIC_DIR):
    """Wrap an ASGI app to also serve the web UI on GET / and GET /index.html.

    Only plain GETs for those two paths are intercepted; everything else
    (JSON-RPC POSTs, the agent card, REST bindings) goes to the A2A app.
    """
    from starlette.responses import FileResponse

    index = static_dir / "index.html"

    async def wrapped(scope, receive, send):
        if (
            scope["type"] == "http"
            and scope["method"] == "GET"
            and scope["path"] in ("/", "/index.html")
        ):
            response = FileResponse(index)
            await response(scope, receive, send)
            return
        await app(scope, receive, send)

    return wrapped


def build_agent_from_env() -> BattleshipAgent:
    """Create a BattleshipAgent configured by environment variables."""
    port = int(os.environ.get("BATTLESHIP_PORT", "8790"))
    return BattleshipAgent(
        name=os.environ.get("BATTLESHIP_NAME", "Capitán A2A"),
        strategy=os.environ.get("BATTLESHIP_STRATEGY", "hunter"),
        url=f"http://localhost:{port}",
    )


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("BATTLESHIP_PORT", "8790"))
    bs = build_agent_from_env()

    print("=" * 60)
    print("Battleship Agent - A2A Lite")
    print("=" * 60)
    print(f"Agent:    {bs.name} (strategy: {bs.strategy_name})")
    print(f"UI:       http://localhost:{port}/")
    print(f"Card:     http://localhost:{port}/.well-known/agent-card.json")
    print("=" * 60)

    # agent.run() cannot serve extra routes, so we build the app manually
    # and wrap it to serve the UI on GET /. A2A traffic is untouched.
    uvicorn.run(with_ui(bs.get_app()), host="0.0.0.0", port=port, log_level="info")
