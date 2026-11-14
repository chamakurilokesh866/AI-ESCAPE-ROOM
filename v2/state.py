"""Structured game state for Version 2.

The whole game lives in one small, JSON-serialisable object. Python reads and
changes it; the LLM never does. Because it is plain data it can be shown in
the UI, saved, compared in tests and checked for contradictions.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field

from v2.room import ITEMS, PUZZLES


def _default_flags() -> dict[str, bool]:
    return {
        "note_read": False,
        "drawer_unlocked": False,
        "compartment_found": False,
        "compartment_open": False,
        "card_read": False,
        "diary_read": False,
        "door_open": False,
    }


@dataclass
class GameState:
    inventory: list[str] = field(default_factory=list)
    examined: list[str] = field(default_factory=list)
    flags: dict[str, bool] = field(default_factory=_default_flags)
    solved: list[str] = field(default_factory=list)
    wrong_attempts: dict[str, int] = field(default_factory=lambda: {"drawer": 0, "door": 0})
    turn: int = 0
    log: list[str] = field(default_factory=list)  # short record of successful actions

    # ---------------------------------------------------------------- helpers
    @property
    def escaped(self) -> bool:
        return self.flags["door_open"]

    def has(self, item: str) -> bool:
        return item in self.inventory

    def mark_examined(self, name: str) -> None:
        if name not in self.examined:
            self.examined.append(name)

    def solve(self, puzzle_id: str) -> None:
        if puzzle_id not in self.solved:
            self.solved.append(puzzle_id)

    def record(self, event: str) -> None:
        self.log.append(event)
        del self.log[:-20]  # keep the log short

    def copy(self) -> "GameState":
        return copy.deepcopy(self)

    # ---------------------------------------------------------- serialisation
    def to_dict(self) -> dict:
        data = asdict(self)
        data["escaped"] = self.escaped
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "GameState":
        data = {k: v for k, v in data.items() if k != "escaped"}
        return cls(**data)

    def progress(self) -> tuple[int, int]:
        """(steps done, total steps): three puzzles plus the escape."""
        return len(self.solved) + int(self.escaped), len(PUZZLES) + 1


def check_invariants(state: GameState) -> list[str]:
    """Return a list of contradictions. An empty list means the state is consistent."""
    problems = []
    f = state.flags
    for item in state.inventory:
        if item not in ITEMS:
            problems.append(f"unknown item in inventory: {item}")
    if len(set(state.inventory)) != len(state.inventory):
        problems.append("duplicate item in inventory")
    if ("brass key" in state.inventory or "index card" in state.inventory) and not f["drawer_unlocked"]:
        problems.append("drawer items collected while drawer is locked")
    if "diary" in state.inventory and not f["compartment_open"]:
        problems.append("diary collected while compartment is closed")
    if f["compartment_open"] and not f["compartment_found"]:
        problems.append("compartment open before it was found")
    if f["card_read"] and "magnifying glass" not in state.inventory:
        problems.append("index card read without the magnifying glass")
    if f["door_open"] and set(state.solved) != set(PUZZLES):
        problems.append("door open before all puzzles were solved")
    for p in state.solved:
        if p not in PUZZLES:
            problems.append(f"unknown puzzle: {p}")
    return problems
