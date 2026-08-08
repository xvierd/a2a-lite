"""
Battleship Arena - agent vs agent over the real A2A protocol.

Launches two BattleshipAgent instances (in threads, on their own ports) and
a spectator server that serves the web UI plus two plain-JSON endpoints
(/arena/state, /arena/new) — the only non-A2A endpoints, allowed for
spectating. All game moves are real A2A SendMessage calls made with the
a2a-lite client (AgentNetwork).

Turn flow (all A2A):
    arena -> next_shot(attacker)
    arena -> receive_shot(defender, row, col)
    arena -> report_shot_result(attacker, row, col, result, ship)

ArenaEngine is decoupled from the transport: it takes an async `call`
callable, so production uses real A2A calls and tests use in-process stubs.

Ports (configurable via env):
    ARENA_PORT        spectator server   (default 8793)
    ARENA_PORT_A      internal agent A   (default 8791)
    ARENA_PORT_B      internal agent B   (default 8792)
"""

from __future__ import annotations

import asyncio
import os
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Callable

import uvicorn

from agent import BattleshipAgent

SIZE = 10

# async (player_name, skill, params) -> result dict
ArenaCaller = Callable[[str, str, dict], Awaitable[Any]]

ROWS = "ABCDEFGHIJ"


def cell_label(row: int, col: int) -> str:
    return f"{ROWS[row]}{col + 1}"


class ArenaEngine:
    """Plays a full Battleship match through a caller, tracking spectator state.

    The caller performs `skill` on `player` and returns the result dict.
    In production it is a real A2A call; in tests it can be a stub.
    """

    def __init__(
        self,
        call: ArenaCaller,
        players: tuple[str, str] = ("A", "B"),
        max_turns: int = 400,
        delay: float = 0.0,
    ):
        self.call = call
        self.players = players
        self.max_turns = max_turns
        self.delay = delay
        self.state: dict[str, Any] = {}
        self._reset_state()

    # ------------------------------------------------------------------
    # Spectator state
    # ------------------------------------------------------------------
    def _reset_state(self) -> None:
        self.state = {
            "status": "starting",
            "turn": 0,
            "winner": None,
            "players": list(self.players),
            "boards": {
                name: [["", "", "", "", "", "", "", "", "", ""] for _ in range(SIZE)]
                for name in self.players
            },
            "log": [],
        }

    def _log(self, message: str) -> None:
        self.state["log"].append(message)
        # Keep the log bounded for the spectator UI.
        if len(self.state["log"]) > 500:
            self.state["log"] = self.state["log"][-500:]

    def snapshot(self) -> dict[str, Any]:
        return self.state

    # ------------------------------------------------------------------
    # Game loop
    # ------------------------------------------------------------------
    async def play(self) -> dict[str, Any]:
        """Play one full match and return the final spectator state."""
        self._reset_state()
        for name in self.players:
            await self.call(name, "new_game", {})
        self._log(f"Nueva batalla: {self.players[0]} vs {self.players[1]}")
        self.state["status"] = "running"

        attacker, defender = self.players
        retries = 0
        while self.state["turn"] < self.max_turns and not self.state["winner"]:
            shot = await self.call(attacker, "next_shot", {})
            row, col = shot["row"], shot["col"]
            result = await self.call(defender, "receive_shot", {"row": row, "col": col})

            if result.get("already_shot"):
                # Should not happen with a sane strategy; do not burn a turn.
                retries += 1
                if retries > 50:
                    self._log("Demasiados disparos repetidos, abortando")
                    self.state["status"] = "finished"
                    return self.state
                continue
            retries = 0

            await self.call(
                attacker,
                "report_shot_result",
                {
                    "row": row,
                    "col": col,
                    "result": result["result"],
                    "ship": result.get("ship") or "",
                },
            )

            outcome = result["result"]
            self.state["boards"][defender][row][col] = outcome
            label = cell_label(row, col)
            if outcome == "miss":
                self._log(f"{attacker}: {label} — Agua 🌊")
            elif outcome == "hit":
                self._log(f"{attacker}: {label} — ¡Tocado! 💥")
            else:
                self._log(f"{attacker}: {label} — ¡Hundido {result.get('ship')}! ☠️")

            self.state["turn"] += 1
            if result.get("game_over"):
                self.state["winner"] = attacker
                self._log(f"🏆 {attacker} gana la batalla en {self.state['turn']} turnos")
                break

            attacker, defender = defender, attacker
            if self.delay:
                await asyncio.sleep(self.delay)

        if not self.state["winner"]:
            self._log("Límite de turnos alcanzado, empate")
        self.state["status"] = "finished"
        return self.state


# ----------------------------------------------------------------------
# Production wiring: two real agents + AgentNetwork caller
# ----------------------------------------------------------------------
def start_agent_in_thread(name: str, strategy: str, port: int) -> uvicorn.Server:
    """Launch a BattleshipAgent (A2A only, no UI) in a daemon thread."""
    bs = BattleshipAgent(name=name, strategy=strategy)
    config = uvicorn.Config(bs.get_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server


def wait_for_agent(url: str, timeout: float = 15.0) -> None:
    """Block until the agent's card endpoint answers (readiness probe)."""
    import httpx

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            response = httpx.get(f"{url}/.well-known/agent-card.json", timeout=2.0)
            if response.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"Agent at {url} did not start within {timeout}s")


def make_a2a_caller(endpoints: dict[str, str]) -> ArenaCaller:
    """Build the production caller: real A2A SendMessage via AgentNetwork."""
    from a2a_lite import AgentNetwork

    network = AgentNetwork(endpoints)

    async def call(player: str, skill: str, params: dict) -> Any:
        return await network.call(player, skill, **params)

    return call


class ArenaManager:
    """Owns the current game task so /arena/new can start a fresh match."""

    def __init__(self, engine: ArenaEngine):
        self.engine = engine
        self._task: asyncio.Task | None = None

    def start_game(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = asyncio.ensure_future(self.engine.play())


def build_spectator_app(manager: ArenaManager, static_dir: Path):
    """Starlette app: UI on GET / plus the two plain-JSON arena endpoints."""
    from starlette.applications import Starlette
    from starlette.responses import FileResponse, JSONResponse
    from starlette.routing import Route

    index = static_dir / "index.html"

    async def serve_index(request):
        return FileResponse(index)

    async def arena_state(request):
        return JSONResponse(manager.engine.snapshot())

    async def arena_new(request):
        manager.start_game()
        return JSONResponse({"ok": True})

    async def on_startup():
        manager.start_game()

    return Starlette(
        routes=[
            Route("/", serve_index, methods=["GET"]),
            Route("/arena/state", arena_state, methods=["GET"]),
            Route("/arena/new", arena_new, methods=["POST"]),
        ],
        on_startup=[on_startup],
    )


def main() -> None:
    static_dir = Path(__file__).parent / "static"

    port_a = int(os.environ.get("ARENA_PORT_A", "8791"))
    port_b = int(os.environ.get("ARENA_PORT_B", "8792"))
    port_arena = int(os.environ.get("ARENA_PORT", "8793"))

    name_a = os.environ.get("ARENA_NAME_A", "Capitán Hunter")
    name_b = os.environ.get("ARENA_NAME_B", "Almirante Random")

    print("=" * 60)
    print("Battleship Arena - A2A Lite (agente vs agente, A2A real)")
    print("=" * 60)
    print(f"Agente A: {name_a} (hunter) en puerto {port_a}")
    print(f"Agente B: {name_b} (random) en puerto {port_b}")

    start_agent_in_thread(name_a, "hunter", port_a)
    start_agent_in_thread(name_b, "random", port_b)

    url_a = f"http://127.0.0.1:{port_a}"
    url_b = f"http://127.0.0.1:{port_b}"
    wait_for_agent(url_a)
    wait_for_agent(url_b)
    print("Agentes listos. Todos los movimientos viajan por A2A SendMessage.")
    print(f"Espectador: http://localhost:{port_arena}/?mode=arena")
    print("=" * 60)

    caller = make_a2a_caller({name_a: url_a, name_b: url_b})
    engine = ArenaEngine(caller, players=(name_a, name_b), delay=0.4)
    manager = ArenaManager(engine)

    uvicorn.run(build_spectator_app(manager, static_dir), host="0.0.0.0", port=port_arena, log_level="info")


if __name__ == "__main__":
    main()
