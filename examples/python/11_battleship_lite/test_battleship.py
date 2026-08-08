"""
Tests for the Battleship A2A Lite example.

Covers:
- Pure game logic (game.py): placement, hit/miss/sunk, game_over, already_shot.
- Strategies (strategy.py): hunter probes adjacent cells after a hit.
- Skills through AgentTestClient: new_game / receive_shot / status / report_shot_result.
- ArenaEngine with in-process stubs: a full match ends with a winner.

Run from the repo root with the package venv:
    packages/python/.venv/bin/python -m pytest examples/python/11_battleship_lite -q
"""

import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from a2a_lite import AgentTestClient  # noqa: E402

from agent import BattleshipAgent  # noqa: E402
from arena import ArenaEngine  # noqa: E402
from game import FLEET, Board  # noqa: E402
from strategy import HunterStrategy, RandomStrategy  # noqa: E402


# ----------------------------------------------------------------------
# game.py — logic
# ----------------------------------------------------------------------
def test_random_fleet_is_valid_and_complete():
    """Random placement: full fleet, in bounds, no overlaps."""
    for seed in range(10):
        board = Board(random.Random(seed))
        assert sorted(s.name for s in board.ships) == sorted(name for name, _ in FLEET)
        occupied = set()
        for ship, (name, length) in zip(board.ships, FLEET):
            assert ship.name == name
            assert len(ship.cells) == length
            for r, c in ship.cells:
                assert 0 <= r < 10 and 0 <= c < 10
                assert (r, c) not in occupied
                occupied.add((r, c))
        assert len(occupied) == sum(length for _, length in FLEET)


def test_miss_hit_sunk_and_game_over():
    board = Board(place_random=False)
    board.add_ship("destroyer", [(0, 0), (0, 1)])
    board.add_ship("submarine", [(2, 2), (3, 2), (4, 2)])

    miss = board.receive_shot(5, 5)
    assert miss["result"] == "miss" and miss["ship"] is None
    assert not miss["game_over"]

    hit = board.receive_shot(0, 0)
    assert hit["result"] == "hit" and hit["ship"] == "destroyer"
    assert hit["cells"] is None

    sunk = board.receive_shot(0, 1)
    assert sunk["result"] == "sunk" and sunk["ship"] == "destroyer"
    assert sunk["cells"] == [[0, 0], [0, 1]]
    assert board.ships_remaining == 1
    assert not board.game_over

    for cell in [(2, 2), (3, 2)]:
        assert board.receive_shot(*cell)["result"] == "hit"
    final = board.receive_shot(4, 2)
    assert final["result"] == "sunk"
    assert final["game_over"] is True
    assert board.game_over


def test_already_shot_returns_clear_error():
    board = Board(random.Random(0))
    first = board.receive_shot(3, 3)
    assert first["ok"] is True
    second = board.receive_shot(3, 3)
    assert second["already_shot"] is True
    assert second["ok"] is False
    # The duplicate shot must not be counted twice.
    assert second["shots_received"] == 1


def test_shot_out_of_bounds_raises():
    board = Board(place_random=False)
    with pytest.raises(ValueError):
        board.receive_shot(10, 0)


# ----------------------------------------------------------------------
# strategy.py — hunter behavior (seeded for determinism)
# ----------------------------------------------------------------------
def test_random_strategy_never_repeats():
    rng = random.Random(42)
    strat = RandomStrategy(rng)
    seen = set()
    for _ in range(100):
        shot = strat.next_shot()
        assert shot not in seen
        seen.add(shot)
        strat.record_result(*shot, "miss")
    assert len(seen) == 100


def test_hunter_probes_adjacent_after_hit():
    rng = random.Random(7)
    strat = HunterStrategy(rng)
    # Hunt until a deterministic "hit" at (5, 5).
    first = strat.next_shot()
    strat.record_result(*first, "miss")
    strat.record_result(5, 5, "hit")

    expected = {(4, 5), (6, 5), (5, 4), (5, 6)}
    for _ in range(4):
        shot = strat.next_shot()
        assert shot in expected, f"expected adjacent target, got {shot}"
        expected.discard(shot)
        strat.record_result(*shot, "miss")


def test_hunter_clears_targets_after_sunk():
    rng = random.Random(11)
    strat = HunterStrategy(rng)
    strat.record_result(5, 5, "hit")
    strat.record_result(5, 6, "sunk", ship="destroyer")
    # After a sink, the queue was cleared: next shot is a fresh hunt cell,
    # not necessarily adjacent to the sunk ship.
    for _ in range(20):
        shot = strat.next_shot()
        assert shot not in strat.shots
        strat.record_result(*shot, "miss")


# ----------------------------------------------------------------------
# Skills via AgentTestClient (real A2A JSON-RPC pipeline, in-process)
# ----------------------------------------------------------------------
@pytest.fixture
def client():
    return AgentTestClient(BattleshipAgent(name="TestBot", strategy="hunter", seed=123).agent)


def test_new_game_skill(client):
    result = client.call("new_game")
    assert result.data == {"ok": True, "ships": 5}


def test_receive_shot_and_status_are_coherent(client):
    client.call("new_game")
    results = [client.call("receive_shot", row=0, col=c).data for c in range(4)]
    for res in results:
        assert res["result"] in ("miss", "hit", "sunk")
    assert results[-1]["shots_received"] == 4

    dup = client.call("receive_shot", row=0, col=0).data
    assert dup["already_shot"] is True

    status = client.call("status").data
    assert status["shots_received"] == 4
    assert status["ships_remaining"] == 5
    assert status["strategy"] == "hunter"


def test_next_shot_and_report_shot_result(client):
    client.call("new_game")
    shot = client.call("next_shot").data
    assert 0 <= shot["row"] < 10 and 0 <= shot["col"] < 10

    ok = client.call("report_shot_result", row=shot["row"], col=shot["col"], result="hit", ship="carrier").data
    assert ok == {"ok": True}

    # After a hit, the hunter must target a neighbor of that hit.
    nxt = client.call("next_shot").data
    dr = abs(nxt["row"] - shot["row"])
    dc = abs(nxt["col"] - shot["col"])
    assert dr + dc == 1

    status = client.call("status").data
    assert status["my_shots"] == 1


def test_full_game_via_skills(client):
    """Shooting every cell sinks the whole fleet and reports game_over."""
    client.call("new_game")
    game_over = False
    for r in range(10):
        for c in range(10):
            res = client.call("receive_shot", row=r, col=c).data
            if res["result"] == "sunk":
                assert res["ship"] in [name for name, _ in FLEET]
                assert len(res["cells"]) > 0
            game_over = res["game_over"]
    assert game_over is True
    status = client.call("status").data
    assert status["ships_remaining"] == 0
    assert status["shots_received"] == 100


def test_agent_card_lists_skills(client):
    card = client.get_agent_card()
    skill_ids = {s["id"] for s in card["skills"]}
    assert {"new_game", "receive_shot", "next_shot", "report_shot_result", "status"} <= skill_ids
    assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"


# ----------------------------------------------------------------------
# ArenaEngine with in-process stubs (no HTTP)
# ----------------------------------------------------------------------
class StubPlayer:
    """In-process stand-in for a remote BattleshipAgent (same contract)."""

    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.board = Board(self.rng)
        self.strategy = HunterStrategy(self.rng)

    async def __call__(self, skill, params):
        if skill == "new_game":
            self.board = Board(self.rng)
            self.strategy = HunterStrategy(self.rng)
            return {"ok": True, "ships": 5}
        if skill == "next_shot":
            r, c = self.strategy.next_shot()
            return {"row": r, "col": c}
        if skill == "receive_shot":
            return self.board.receive_shot(params["row"], params["col"])
        if skill == "report_shot_result":
            self.strategy.record_result(
                params["row"], params["col"], params["result"], params.get("ship") or None
            )
            return {"ok": True}
        raise ValueError(f"unknown skill {skill}")


@pytest.mark.asyncio
async def test_arena_engine_full_match_with_stubs():
    players = {"A": StubPlayer(seed=1), "B": StubPlayer(seed=2)}

    async def call(player, skill, params):
        return await players[player](skill, params)

    engine = ArenaEngine(call, players=("A", "B"))
    state = await engine.play()

    assert state["status"] == "finished"
    assert state["winner"] in ("A", "B")
    assert state["turn"] < 200
    assert state["log"], "the spectator log must contain moves"

    loser = "B" if state["winner"] == "A" else "A"
    loser_board = state["boards"][loser]
    hits = sum(cell in ("hit", "sunk") for row in loser_board for cell in row)
    assert hits == sum(length for _, length in FLEET)
