"""
Battleship game logic - pure Python, no A2A dependencies.

Board 10x10 with the standard fleet:
    carrier 5, battleship 4, cruiser 3, submarine 3, destroyer 2
"""

from __future__ import annotations

import random

SIZE = 10

# (name, length) — Spanish display names kept in the UI layer.
FLEET: list[tuple[str, int]] = [
    ("carrier", 5),
    ("battleship", 4),
    ("cruiser", 3),
    ("submarine", 3),
    ("destroyer", 2),
]

MISS = "miss"
HIT = "hit"
SUNK = "sunk"


class Ship:
    """A placed ship: its cells and which of them have been hit."""

    def __init__(self, name: str, cells: list[tuple[int, int]]):
        self.name = name
        self.cells = list(cells)
        self.hits: set[tuple[int, int]] = set()

    @property
    def sunk(self) -> bool:
        return len(self.hits) == len(self.cells)


class Board:
    """Own board: fleet placement + incoming-shot bookkeeping."""

    SIZE = SIZE

    def __init__(self, rng: random.Random | None = None, place_random: bool = True):
        self._rng = rng or random.Random()
        self.ships: list[Ship] = []
        self._grid: dict[tuple[int, int], Ship] = {}
        self.shots_received: set[tuple[int, int]] = set()
        if place_random:
            self.place_fleet_random()

    # ------------------------------------------------------------------
    # Placement
    # ------------------------------------------------------------------
    def add_ship(self, name: str, cells: list[tuple[int, int]]) -> None:
        """Manually place a ship (used by tests). Validates bounds and overlap."""
        for r, c in cells:
            if not (0 <= r < SIZE and 0 <= c < SIZE):
                raise ValueError(f"Cell ({r},{c}) out of bounds")
            if (r, c) in self._grid:
                raise ValueError(f"Cell ({r},{c}) already occupied")
        ship = Ship(name, cells)
        self.ships.append(ship)
        for cell in cells:
            self._grid[cell] = ship

    def place_fleet_random(self) -> None:
        """Place the standard fleet at random valid positions."""
        for name, length in FLEET:
            placed = False
            while not placed:
                horizontal = self._rng.random() < 0.5
                r = self._rng.randrange(SIZE)
                c = self._rng.randrange(SIZE)
                cells = (
                    [(r, c + i) for i in range(length)]
                    if horizontal
                    else [(r + i, c) for i in range(length)]
                )
                if all(
                    0 <= rr < SIZE and 0 <= cc < SIZE and (rr, cc) not in self._grid
                    for rr, cc in cells
                ):
                    self.add_ship(name, cells)
                    placed = True

    # ------------------------------------------------------------------
    # Shooting
    # ------------------------------------------------------------------
    @property
    def game_over(self) -> bool:
        return bool(self.ships) and all(ship.sunk for ship in self.ships)

    @property
    def ships_remaining(self) -> int:
        return sum(1 for ship in self.ships if not ship.sunk)

    def receive_shot(self, row: int, col: int) -> dict:
        """Apply an incoming shot and return the wire-friendly result dict."""
        if not (0 <= row < SIZE and 0 <= col < SIZE):
            raise ValueError(f"Shot ({row},{col}) out of bounds")

        cell = (row, col)
        if cell in self.shots_received:
            return {
                "ok": False,
                "already_shot": True,
                "error": f"Cell ({row},{col}) was already shot",
                "shots_received": len(self.shots_received),
                "game_over": self.game_over,
            }

        self.shots_received.add(cell)
        ship = self._grid.get(cell)

        if ship is None:
            result = MISS
            ship_name = None
            cells = None
        else:
            ship.hits.add(cell)
            ship_name = ship.name
            if ship.sunk:
                result = SUNK
                cells = [list(c) for c in ship.cells]
            else:
                result = HIT
                cells = None

        return {
            "ok": True,
            "already_shot": False,
            "result": result,
            "ship": ship_name,
            "cells": cells,
            "game_over": self.game_over,
            "shots_received": len(self.shots_received),
        }
