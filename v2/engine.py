"""Rule engine for Version 2: Python decides what happens.

``apply(state, action)`` validates a parsed player action against the game
state, changes the state only when the action is allowed, and returns an
``Outcome``. The outcome contains

* ``message``: a complete, correct description of the result (used directly
  when Gemini is unavailable), and
* ``facts``: the only information the narrator LLM may use.

No LLM is involved here, so the rules cannot be talked around.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from v2.room import ALIASES, ALL_NAMES, DESCRIPTIONS, HIDDEN_OBJECTS, ITEMS, OBJECTS, SECRETS
from v2.state import GameState

VERBS = (
    "look", "examine", "take", "read", "use", "open", "enter_code",
    "inventory", "hint", "help", "unknown",
)


@dataclass
class Action:
    verb: str = "unknown"
    target: str | None = None   # object or item the action is aimed at
    item: str | None = None     # item being used (for "use X on Y")
    code: str | None = None     # digits typed on a keypad / lock
    raw_target: str | None = None  # what the player called it, if not a known name


@dataclass
class Outcome:
    ok: bool
    kind: str
    message: str
    facts: list[str] = field(default_factory=list)
    escaped: bool = False


def normalise(name: str | None) -> str | None:
    """Map a player's word ("key", "portrait") to a canonical name, or None."""
    if not name:
        return None
    text = name.lower().strip()
    if text in ALL_NAMES:
        return text
    # longest alias first so "brass key" beats "key"
    pairs = sorted(
        ((alias, canon) for canon, aliases in ALIASES.items() for alias in aliases),
        key=lambda p: -len(p[0]),
    )
    for alias, canon in pairs:
        if re.search(rf"\b{re.escape(alias)}\b", text):
            return canon
    return None


# --------------------------------------------------------------- visibility
def _object_known(state: GameState, obj: str) -> bool:
    if obj not in HIDDEN_OBJECTS:
        return True
    return state.flags["compartment_found"]


def _item_visible(state: GameState, item: str) -> bool:
    """Is the item lying somewhere the player has already discovered?"""
    if state.has(item):
        return False
    where = ITEMS[item]
    if where == "desk":
        return "desk" in state.examined
    if where == "drawer":
        return state.flags["drawer_unlocked"]
    if where == "compartment":
        return state.flags["compartment_open"]
    return False


def _accessible(state: GameState, item: str) -> bool:
    return state.has(item) or _item_visible(state, item)


def _known(state: GameState, name: str | None) -> bool:
    if name is None:
        return False
    if name in OBJECTS:
        return _object_known(state, name)
    return name in ITEMS


def _no_such(action: Action, name: str | None = None) -> Outcome:
    shown = action.raw_target or name or "that"
    return Outcome(
        False, "unknown_object",
        f"There is no {shown} here. You can see a desk, a bookshelf, a painting, "
        "a drawer and the door.",
        [f"The player looked for '{shown}', which does not exist in this room."],
    )


# ------------------------------------------------------------------ actions
def _look(state: GameState, action: Action) -> Outcome:
    text = DESCRIPTIONS["room"]
    if state.flags["compartment_found"]:
        text += " Behind the painting is a small metal compartment."
    return Outcome(True, "look", text, [text])


def _examine(state: GameState, action: Action) -> Outcome:
    t = action.target
    if not _known(state, t):
        return _no_such(action, t)
    if t in ITEMS:
        if not _accessible(state, t):
            return Outcome(False, "not_visible", f"You don't see a {t} anywhere yet.",
                           [f"The {t} has not been found yet."])
        if t in ("note", "index card", "diary"):
            return _read(state, action)
        state.mark_examined(t)
        return Outcome(True, "examine", DESCRIPTIONS[t], [DESCRIPTIONS[t]])

    state.mark_examined(t)
    if t == "desk":
        left = [i for i in ("note", "magnifying glass") if not state.has(i)]
        text = DESCRIPTIONS["desk"] if len(left) == 2 else (
            DESCRIPTIONS["desk_empty"] if not left
            else f"An old mahogany desk with a built-in drawer. A {left[0]} lies on top."
        )
        return Outcome(True, "examine", text, [text])
    if t == "painting":
        first = not state.flags["compartment_found"]
        state.flags["compartment_found"] = True
        if first:
            state.record("found the compartment behind the painting")
        return Outcome(True, "examine", DESCRIPTIONS["painting"], [DESCRIPTIONS["painting"]])
    if t == "drawer":
        if not state.flags["drawer_unlocked"]:
            return Outcome(True, "examine", DESCRIPTIONS["drawer_locked"], [DESCRIPTIONS["drawer_locked"]])
        return Outcome(True, "examine", _container_text(state, "drawer"), [_container_text(state, "drawer")])
    if t == "compartment":
        if not state.flags["compartment_open"]:
            return Outcome(True, "examine", DESCRIPTIONS["compartment_locked"],
                           [DESCRIPTIONS["compartment_locked"]])
        return Outcome(True, "examine", _container_text(state, "compartment"),
                       [_container_text(state, "compartment")])
    return Outcome(True, "examine", DESCRIPTIONS[t], [DESCRIPTIONS[t]])


def _container_text(state: GameState, where: str) -> str:
    base = DESCRIPTIONS[f"{where}_open"]
    inside = [i for i, loc in ITEMS.items() if loc == where and not state.has(i)]
    if inside:
        return f"{base} Inside: {', '.join('a ' + i for i in inside)}."
    return f"{base} It is empty now."


def _take(state: GameState, action: Action) -> Outcome:
    t = action.target
    if not _known(state, t):
        return _no_such(action, t)
    if t in OBJECTS:
        return Outcome(False, "not_takeable", f"The {t} is fixed in place. You can't take it.",
                       [f"The {t} cannot be picked up."])
    if state.has(t):
        return Outcome(False, "already_have", f"You already have the {t}.",
                       [f"The player already carries the {t}."])
    if not _item_visible(state, t):
        return Outcome(False, "not_visible",
                       f"You don't see a {t} anywhere. Keep exploring the room.",
                       [f"The {t} has not been discovered, so it cannot be taken."])
    state.inventory.append(t)
    state.record(f"took the {t}")
    return Outcome(True, "take", f"You take the {t}.", [f"The player picks up the {t}."])


def _read(state: GameState, action: Action) -> Outcome:
    t = action.target
    if t not in ("note", "index card", "diary"):
        if _known(state, t):
            return _examine(state, Action("examine", t))
        return _no_such(action, t)
    if not _accessible(state, t):
        return Outcome(False, "not_visible", f"You don't have a {t} to read.",
                       [f"The {t} has not been found yet."])
    state.mark_examined(t)
    if t == "note":
        state.flags["note_read"] = True
        return Outcome(True, "read", DESCRIPTIONS["note"], [DESCRIPTIONS["note"]])
    if t == "index card":
        if not state.has("magnifying glass"):
            return Outcome(False, "too_small", DESCRIPTIONS["index card_blurry"],
                           [DESCRIPTIONS["index card_blurry"]])
        new = not state.flags["card_read"]
        state.flags["card_read"] = True
        state.solve("tiny_writing")
        if new:
            state.record("read the index card with the magnifying glass")
        return Outcome(True, "puzzle_solved" if new else "read", DESCRIPTIONS["index card"],
                       [DESCRIPTIONS["index card"]])
    # diary
    new = not state.flags["diary_read"]
    state.flags["diary_read"] = True
    state.solve("hidden_compartment")
    if new:
        state.record("read the librarian's diary")
    return Outcome(True, "puzzle_solved" if new else "read", DESCRIPTIONS["diary"],
                   [DESCRIPTIONS["diary"]])


def _open_compartment(state: GameState) -> Outcome:
    if state.flags["compartment_open"]:
        return Outcome(False, "already_open", "The compartment is already open.",
                       [_container_text(state, "compartment")])
    state.flags["compartment_open"] = True
    state.record("opened the compartment with the brass key")
    text = "The brass key turns with a click and the compartment swings open. Inside lies the librarian's diary."
    return Outcome(True, "unlock", text, [text])


def _use(state: GameState, action: Action) -> Outcome:
    item, target = action.item, action.target
    if item is None and target in ITEMS:      # "use the key" with no target
        item, target = target, None
    if item is None or item not in ITEMS:
        return _no_such(action, item)
    if not state.has(item):
        return Outcome(False, "not_in_inventory",
                       f"You don't have the {item}. You can only use items you have collected.",
                       [f"The player tried to use the {item} but does not carry it."])
    if target is None:
        return Outcome(False, "need_target", f"What do you want to use the {item} on?",
                       [f"The player holds the {item} but did not say what to use it on."])
    if not _known(state, target):
        return _no_such(action, target)

    if item == "magnifying glass" and target == "index card":
        return _read(state, Action("read", "index card"))
    if item == "brass key" and target in ("painting", "compartment"):
        if not state.flags["compartment_found"]:
            return Outcome(False, "nothing_happens",
                           "You don't see anywhere on the painting to use a key.",
                           ["There is no visible keyhole on the front of the painting."])
        return _open_compartment(state)
    if item == "brass key" and target in ("drawer", "door"):
        return Outcome(False, "nothing_happens",
                       f"The brass key doesn't fit the {target}. It needs a four-digit code.",
                       [f"The {target} has a keypad/combination lock, not a keyhole."])
    return Outcome(False, "nothing_happens", f"Using the {item} on the {target} does nothing.",
                   [f"Nothing happens when the {item} is used on the {target}."])


def _open(state: GameState, action: Action) -> Outcome:
    t = action.target
    if not _known(state, t):
        return _no_such(action, t)
    if t == "drawer":
        if state.flags["drawer_unlocked"]:
            return _examine(state, Action("examine", "drawer"))
        return Outcome(False, "locked", "The drawer is locked. It needs a four-digit combination.",
                       [DESCRIPTIONS["drawer_locked"]])
    if t == "compartment":
        if state.has("brass key"):
            return _open_compartment(state)
        return Outcome(False, "locked", "The compartment is locked. It needs a key.",
                       [DESCRIPTIONS["compartment_locked"]])
    if t == "door":
        return Outcome(False, "locked", "The door is locked. The keypad needs a four-digit code.",
                       [DESCRIPTIONS["door"]])
    if t == "painting":
        return _examine(state, Action("examine", "painting"))
    return Outcome(False, "nothing_happens", f"You can't open the {t}.", [f"The {t} can't be opened."])


def _clues_found(state: GameState, lock: str) -> bool:
    if lock == "drawer":
        return "bookshelf" in state.examined and state.flags["note_read"]
    return {"season_books", "tiny_writing", "hidden_compartment"} <= set(state.solved)


def _enter_code(state: GameState, action: Action) -> Outcome:
    code = re.sub(r"\D", "", action.code or "")
    lock = action.target
    if lock not in ("drawer", "door"):
        lock = "drawer" if not state.flags["drawer_unlocked"] else "door"
    if len(code) != 4:
        return Outcome(False, "bad_code", f"The {lock} needs exactly four digits.",
                       [f"The {lock} lock only accepts four-digit codes."])
    if lock == "drawer" and state.flags["drawer_unlocked"]:
        return Outcome(False, "already_open", "The drawer is already unlocked.",
                       [_container_text(state, "drawer")])

    correct = code == SECRETS[lock]
    if correct and _clues_found(state, lock):
        if lock == "drawer":
            state.flags["drawer_unlocked"] = True
            state.solve("season_books")
            state.wrong_attempts["drawer"] = 0
            state.record("unlocked the drawer")
            text = ("The combination lock clicks and the drawer slides open. "
                    "Inside: a small brass key and a yellowed index card.")
            return Outcome(True, "puzzle_solved", text, [text])
        state.flags["door_open"] = True
        state.record("opened the door")
        text = "The keypad turns green, the lock clunks open and the heavy oak door swings wide. You are free!"
        return Outcome(True, "escaped", text, [text], escaped=True)

    # Wrong code, or a correct code typed before the clues were found
    # (a guess or a leaked answer). Both get exactly the same response so the
    # lock never reveals whether a guess was right.
    state.wrong_attempts[lock] += 1
    msg = (f"You enter {code}. The {lock} {'lock does not budge' if lock == 'drawer' else 'keypad beeps red'}. "
           "Wrong code.")
    if not _clues_found(state, lock):
        msg += " You haven't found enough clues to work this code out yet."
    elif state.wrong_attempts[lock] >= 3:
        msg += " Type 'hint' if you're stuck."
    return Outcome(False, "wrong_code", msg, [msg])


def _inventory(state: GameState, action: Action) -> Outcome:
    if not state.inventory:
        return Outcome(True, "inventory", "You are not carrying anything yet.", [])
    return Outcome(True, "inventory", "You are carrying: " + ", ".join(state.inventory) + ".", [])


def next_hint(state: GameState) -> str:
    f = state.flags
    if "desk" not in state.examined:
        return "Start by examining the desk."
    if not f["note_read"]:
        return "There's a note on the desk. Try reading it."
    if "bookshelf" not in state.examined:
        return "The bookshelf deserves a closer look."
    if not f["drawer_unlocked"]:
        return ("Each sticking-out book has a digit, and the note tells you an order. "
                "Put the digits in that order and try them on the drawer.")
    if not state.has("magnifying glass"):
        return "Take the magnifying glass from the desk. It will help later."
    if not state.has("index card") or not state.has("brass key"):
        return "Take what's inside the drawer."
    if not f["card_read"]:
        return "The index card's writing is tiny. Something you carry could help you read it."
    if not f["compartment_found"]:
        return "Paintings sometimes hide things. Examine the painting."
    if not f["compartment_open"]:
        return "The compartment behind the painting has a keyhole. Do you have a key?"
    if not f["diary_read"]:
        return "Take the diary and read it."
    return ("The card said the door remembers the librarian's birth year, and the diary "
            "gives it in Roman numerals. Convert it and enter it on the door keypad.")


def _hint(state: GameState, action: Action) -> Outcome:
    return Outcome(True, "hint", "Hint: " + next_hint(state), [])


HELP_TEXT = (
    "Type what you want to do in plain English, for example: 'examine the desk', "
    "'take the magnifying glass', 'read the note', 'use the brass key on the compartment', "
    "'enter 1234 on the drawer'. Commands: 'look', 'inventory', 'hint', 'help'."
)


def _help(state: GameState, action: Action) -> Outcome:
    return Outcome(True, "help", HELP_TEXT, [])


def _unknown(state: GameState, action: Action) -> Outcome:
    return Outcome(False, "unknown_action",
                   "Nothing happens. Try examining, taking, reading or using something, "
                   "or type 'hint'.",
                   ["The game did not understand the player's action."])


HANDLERS = {
    "look": _look, "examine": _examine, "take": _take, "read": _read, "use": _use,
    "open": _open, "enter_code": _enter_code, "inventory": _inventory,
    "hint": _hint, "help": _help, "unknown": _unknown,
}


def apply(state: GameState, action: Action) -> Outcome:
    """Validate and apply one action. Mutates ``state`` only for allowed actions."""
    if state.escaped:
        return Outcome(True, "already_escaped",
                       "You have already escaped! Press 'Restart game' to play again.", [],
                       escaped=True)
    state.turn += 1
    handler = HANDLERS.get(action.verb, _unknown)
    return handler(state, action)
