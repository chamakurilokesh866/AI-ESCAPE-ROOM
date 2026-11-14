"""The Version 2 turn pipeline.

    player text
      -> guardrails.check_input      (Python: refuse injection / cheating)
      -> parser.parse                (Gemini JSON intent, or keyword fallback)
      -> engine.apply                (Python: validate + update state)
      -> state.check_invariants      (Python: roll back if contradictory)
      -> narrator.narrate            (Gemini: describe the verified result)
      -> guardrails.check_narration  (Python: block leaks, else use template)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from v2 import engine, guardrails, narrator, parser
from v2.llm import LLMError
from v2.room import INTRO, TITLE
from v2.state import GameState, check_invariants

DETERMINISTIC_KINDS = {"inventory", "hint", "help", "already_escaped"}

OPENING_MESSAGE = (
    f"**{TITLE}**\n\n{INTRO}\n\n"
    "_What do you want to do? Try something like \"examine the desk\"._"
)


@dataclass
class TurnResult:
    reply: str
    action: engine.Action | None = None
    outcome: engine.Outcome | None = None
    blocked: str = ""             # guardrail reason if refused
    parser_source: str = ""       # 'gemini' or 'local'
    narrated_by: str = ""         # 'gemini' or 'engine'
    notices: list[str] = field(default_factory=list)  # warnings for the UI

    @property
    def escaped(self) -> bool:
        return bool(self.outcome and self.outcome.escaped)


class Game:
    def __init__(self, llm=None):
        self.llm = llm  # None -> offline mode (keyword parser + engine text)
        self.state = GameState()
        self.recent: list[tuple[str, str]] = []  # (player, reply), last few turns only
        self.last_player_message: str | None = None

    @property
    def offline(self) -> bool:
        return self.llm is None

    def _remember(self, player: str, reply: str) -> None:
        self.recent.append((player, reply))
        del self.recent[:-narrator.CONTEXT_TURNS]
        self.last_player_message = player

    def turn(self, text: str) -> TurnResult:
        text = (text or "").strip()
        check = guardrails.check_input(text)
        if not check.allowed:
            result = TurnResult(check.message, blocked=check.reason)
            if check.reason == "rule_bypass":
                self._remember(text, "(refused)")
            return result

        notices: list[str] = []
        # 1. Parse intent
        try:
            action, cheat, source = parser.parse(self.llm, text, self.last_player_message)
        except (LLMError, parser.ParseError) as exc:
            message = getattr(exc, "user_message", str(exc))
            notices.append(f"{message} Using the offline parser for this turn.")
            action, cheat, source = parser.local_parse(text), False, "local"
        if cheat:
            self._remember(text, "(refused)")
            return TurnResult(guardrails.REFUSAL_MESSAGE, blocked="rule_bypass_llm",
                              parser_source=source, notices=notices)

        # 2. Validate and apply in Python
        snapshot = self.state.copy()
        outcome = engine.apply(self.state, action)
        problems = check_invariants(self.state)
        if problems:  # should never happen; never keep a contradictory state
            self.state = snapshot
            outcome = engine.Outcome(False, "rejected", "That can't happen. Nothing changes.", [])
            notices.append("Inconsistent state detected and rolled back: " + "; ".join(problems))

        # 3. Narrate the verified result
        reply, narrated_by = outcome.message, "engine"
        if self.llm is not None and outcome.kind not in DETERMINISTIC_KINDS:
            try:
                text_out = narrator.narrate(self.llm, self.state, outcome, text, self.recent)
                ok, reason = guardrails.check_narration(text_out, self.state, text)
                if ok:
                    reply, narrated_by = text_out, "gemini"
                elif reason == "leaked_code":
                    notices.append("Narration hid a secret code, so the game's own text was used.")
            except LLMError as exc:
                notices.append(f"{exc.user_message} Showing the game's own description instead.")
        if check.claim:
            reply = f"{reply}\n\n{guardrails.CLAIM_NOTE}"

        self._remember(text, reply)
        return TurnResult(reply, action, outcome, parser_source=source,
                          narrated_by=narrated_by, notices=notices)
