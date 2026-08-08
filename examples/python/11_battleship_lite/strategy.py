"""
Shooting strategies for the Battleship agent.

A strategy tracks the shots *this agent has fired* at the opponent:
- next_shot() picks the next coordinate to fire at.
- record_result() feeds the outcome back so the strategy can adapt.

Both strategies accept a random.Random instance so tests can be seeded.
"""

from __future__ import annotations

import random
from collections import deque

SIZE = 10


def make_strategy(name: str, rng: random.Random | None = None):
    """Factory: 'hunter' (default) or 'random'."""
    rng = rng or random.Random()
    if name == "random":
        return RandomStrategy(rng)
    if name == "hunter":
        return HunterStrategy(rng)
    raise ValueError(f"Unknown strategy: {name!r} (use 'hunter' or 'random')")


class RandomStrategy:
    """Fires at random untried cells."""

    name = "random"

    def __init__(self, rng: random.Random):
        self._rng = rng
        self.shots: set[tuple[int, int]] = set()

    def next_shot(self) -> tuple[int, int]:
        available = [
            (r, c)
            for r in range(SIZE)
            for c in range(SIZE)
            if (r, c) not in self.shots
        ]
        if not available:
            raise RuntimeError("No cells left to shoot")
        return self._rng.choice(available)

    def record_result(self, row: int, col: int, result: str, ship: str | None = None) -> None:
        self.shots.add((row, col))


class HunterStrategy(RandomStrategy):
    """Hunt/target: fires randomly until a hit, then probes adjacent cells.

    After a hit, the orthogonally adjacent untried cells are queued as
    targets. When a ship sinks, the pending target queue is cleared and
    the strategy goes back to hunting at random. Simple but effective.
    """

    name = "hunter"

    def __init__(self, rng: random.Random):
        super().__init__(rng)
        self._targets: deque[tuple[int, int]] = deque()

    def next_shot(self) -> tuple[int, int]:
        while self._targets:
            cell = self._targets.popleft()
            if cell not in self.shots:
                return cell
        return super().next_shot()

    def record_result(self, row: int, col: int, result: str, ship: str | None = None) -> None:
        self.shots.add((row, col))
        if result == "hit":
            neighbors = [(row - 1, col), (row + 1, col), (row, col - 1), (row, col + 1)]
            self._rng.shuffle(neighbors)
            for cell in neighbors:
                r, c = cell
                if 0 <= r < SIZE and 0 <= c < SIZE and cell not in self.shots:
                    self._targets.append(cell)
        elif result == "sunk":
            # The current target is destroyed: drop pending probes and
            # resume hunting at random.
            self._targets.clear()
