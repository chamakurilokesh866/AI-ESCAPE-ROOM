"""Guardrails for Version 2.

Two layers around the LLM:

1. ``check_input`` runs *before* Gemini. Obvious rule-breaking messages
   (prompt injection, admin impersonation, asking for codes/solutions,
   "unlock it immediately") are refused in Python and never reach the model.
   Claims about progress ("I already have the key") are not refused, but are
   flagged: the action is still validated against the real game state.
2. ``check_narration`` runs *after* Gemini. If the narration leaks a code the
   player has not earned, or is empty/too long, it is replaced by the
   engine's deterministic message.

Even if both layers missed something, the LLM still cannot change the game:
only the Python engine can modify the state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from v2.room import SECRETS
from v2.state import GameState

MAX_INPUT_CHARS = 400
MAX_NARRATION_CHARS = 900

_INJECTION_PATTERNS = [
    r"\bignore\b.{0,40}\b(instruction|rule|prompt|previous|above|system)",
    r"\b(disregard|forget|override|bypass)\b.{0,40}\b(instruction|rule|prompt|restriction)",
    r"\bsystem prompt\b|\byour (prompt|instructions)\b",
    r"\b(i am|i'm|im|as)\b.{0,20}\b(admin|administrator|developer|game ?master|moderator|creator|teacher|god mode)\b",
    r"\b(admin|developer|debug|god|cheat)\s*(mode|access|command|override)\b",
    r"\b(jailbreak|dan mode|you are now|pretend (you|to be)|act as)\b",
    r"\b(reveal|tell|give|show|list|print|say|what(?:'s| is| are))\b.{0,40}\b(secret|code|codes|combination|password|solution|solutions|answer|answers)\b",
    r"\b(unlock|open)\b.{0,30}\b(immediately|right now|now|instantly)\b",
    r"\b(skip|solve|complete|finish)\b.{0,20}\b(puzzle|puzzles|game|level|it) for me\b",
    r"\b(mark|set|consider)\b.{0,30}\b(solved|unlocked|completed|escaped)\b",
]

_CLAIM_PATTERNS = [
    r"\bi (already|have already|already have|previously)\b",
    r"\b(already|previously)\b.{0,30}\b(solved|opened|unlocked|found|have|took|got)\b",
    r"\b(we|i) (did|have done) (that|this) (before|already)\b",
]

_REFUSAL = (
    "🛡️ The Game Master only describes the room. Rules, codes and the door are "
    "controlled by the game itself, so they can't be changed by asking. "
    "Keep exploring, or type **hint** for a nudge."
)


@dataclass
class InputCheck:
    allowed: bool
    reason: str = ""
    message: str = ""
    claim: bool = False


def check_input(text: str) -> InputCheck:
    stripped = text.strip()
    if not stripped:
        return InputCheck(False, "empty", "Type what you want to do, for example 'examine the desk'.")
    if len(stripped) > MAX_INPUT_CHARS:
        return InputCheck(False, "too_long",
                          f"That's a lot of text! Please describe one action in under {MAX_INPUT_CHARS} characters.")
    low = stripped.lower()
    for pattern in _INJECTION_PATTERNS:
        if re.search(pattern, low):
            return InputCheck(False, "rule_bypass", _REFUSAL)
    claim = any(re.search(p, low) for p in _CLAIM_PATTERNS)
    return InputCheck(True, claim=claim)


CLAIM_NOTE = "_(The game keeps its own record of what you've done, so claims about earlier progress don't change anything.)_"
REFUSAL_MESSAGE = _REFUSAL


_DIGIT_SEPARATORS = re.compile(r"(?<=\d)[\s\-.,/_|:]+(?=\d)")
_TRAILING_DIGITS = re.compile(r"\d[\d\s\-.,/_|:]*$")


def _collapse_digits(text: str) -> str:
    """Remove separators between digits, so any spacing of a code becomes '1847'."""
    return _DIGIT_SEPARATORS.sub("", text)


def _variants(code: str) -> list[str]:
    spaced = " ".join(code)
    return [code, spaced, "-".join(code), f"{code[:2]} {code[2:]}"]


def unearned_codes(state: GameState) -> list[str]:
    hidden = []
    if not state.flags["drawer_unlocked"]:
        hidden.append(SECRETS["drawer"])
    if not state.flags["door_open"]:
        hidden.append(SECRETS["door"])
    return hidden


def check_narration(text: str | None, state: GameState, player_message: str = "") -> tuple[bool, str]:
    """Return (ok, reason). ``ok`` is False when the narration must be replaced."""
    if not text or not text.strip():
        return False, "empty"
    if len(text) > MAX_NARRATION_CHARS:
        return False, "too_long"
    player_digits = re.sub(r"\D", "", player_message)
    for code in unearned_codes(state):
        if code in player_digits:
            continue  # the player typed it themselves; echoing it reveals nothing
        for variant in _variants(code):
            if variant in text:
                return False, "leaked_code"
        if code in _collapse_digits(text):  # "58-42", "5 - 8 - 4 - 2", "5.8.4.2", ...
            return False, "leaked_code"
    return True, ""


class StreamGuard:
    """Applies ``check_narration`` to text that is streamed to the screen.

    Each chunk is added to a buffer and the whole buffer is checked before
    anything is shown. A run of digits at the end of the buffer is held back
    until it is complete (a non-digit follows), so even the first digits of a
    code that is still being written never reach the player. If a leak (or runaway length) is detected, the
    stream is stopped and the caller replaces the text with the engine's own.
    """

    def __init__(self, state: GameState, player_message: str = ""):
        self.state = state
        self.player_message = player_message
        self.text = ""
        self.blocked = ""

    def feed(self, chunk: str) -> str | None:
        """Add a chunk. Returns the text that is safe to display, or None if blocked."""
        if self.blocked:
            return None
        self.text += chunk
        ok, reason = check_narration(self.text, self.state, self.player_message)
        if not ok and reason in ("leaked_code", "too_long"):
            self.blocked = reason
            return None
        trailing = _TRAILING_DIGITS.search(self.text)
        return self.text[:trailing.start()] if trailing else self.text

    def finish(self) -> tuple[bool, str]:
        """Final check on the complete text: (ok, reason)."""
        if self.blocked:
            return False, self.blocked
        return check_narration(self.text, self.state, self.player_message)
