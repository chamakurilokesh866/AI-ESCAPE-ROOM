"""Offline tests for the V2 rule engine and game state (no LLM involved)."""

import json
import unittest

from v2.engine import Action, apply, next_hint, normalise
from v2.room import ITEMS, OBJECTS, PUZZLES, SECRETS
from v2.state import GameState, check_invariants

SOLUTION = [
    Action("examine", "desk"),
    Action("read", "note"),
    Action("examine", "bookshelf"),
    Action("enter_code", "drawer", code=SECRETS["drawer"]),
    Action("take", "magnifying glass"),
    Action("take", "brass key"),
    Action("take", "index card"),
    Action("use", "index card", item="magnifying glass"),
    Action("examine", "painting"),
    Action("use", "compartment", item="brass key"),
    Action("take", "diary"),
    Action("read", "diary"),
    Action("enter_code", "door", code=SECRETS["door"]),
]


def play(actions, state=None):
    state = state or GameState()
    outcomes = [apply(state, a) for a in actions]
    return state, outcomes


class RoomTests(unittest.TestCase):
    def test_assignment_minimums(self):
        visible_objects = [o for o in OBJECTS if o != "compartment"]
        self.assertGreaterEqual(len(visible_objects), 5)
        self.assertGreaterEqual(len(PUZZLES), 3)
        self.assertGreaterEqual(len(ITEMS), 3)

    def test_aliases(self):
        self.assertEqual(normalise("the key"), "brass key")
        self.assertEqual(normalise("portrait"), "painting")
        self.assertEqual(normalise("keypad"), "door")
        self.assertEqual(normalise("magnifier"), "magnifying glass")
        self.assertIsNone(normalise("window"))


class PlaythroughTests(unittest.TestCase):
    def test_full_solution_escapes(self):
        state, outcomes = play(SOLUTION)
        self.assertTrue(all(o.ok for o in outcomes), [o.message for o in outcomes if not o.ok])
        self.assertTrue(state.escaped)
        self.assertTrue(outcomes[-1].escaped)
        self.assertEqual(set(state.solved), set(PUZZLES))
        self.assertEqual(state.progress(), (4, 4))
        self.assertEqual(check_invariants(state), [])

    def test_actions_after_escape_do_nothing(self):
        state, _ = play(SOLUTION)
        before = state.to_dict()
        out = apply(state, Action("take", "note"))
        self.assertEqual(out.kind, "already_escaped")
        self.assertEqual(state.to_dict(), before)

    def test_state_is_json_round_trip(self):
        state, _ = play(SOLUTION[:6])
        again = GameState.from_dict(json.loads(state.to_json()))
        self.assertEqual(again.to_dict(), state.to_dict())

    def test_hints_never_contain_codes(self):
        state = GameState()
        for a in SOLUTION:
            hint = next_hint(state)
            for code in SECRETS.values():
                self.assertNotIn(code, hint)
            apply(state, a)


class ValidationTests(unittest.TestCase):
    def test_cannot_use_item_not_collected(self):
        state, (out,) = play([Action("use", "painting", item="brass key")])
        self.assertFalse(out.ok)
        self.assertEqual(out.kind, "not_in_inventory")
        self.assertEqual(state.inventory, [])

    def test_cannot_take_items_from_locked_drawer(self):
        state, (out,) = play([Action("take", "brass key")])
        self.assertEqual(out.kind, "not_visible")
        self.assertNotIn("brass key", state.inventory)

    def test_cannot_take_desk_items_before_seeing_them(self):
        _, (out,) = play([Action("take", "magnifying glass")])
        self.assertEqual(out.kind, "not_visible")

    def test_wrong_drawer_code(self):
        state, outs = play(SOLUTION[:3] + [Action("enter_code", "drawer", code="1234")])
        self.assertEqual(outs[-1].kind, "wrong_code")
        self.assertFalse(state.flags["drawer_unlocked"])
        self.assertEqual(state.wrong_attempts["drawer"], 1)

    def test_correct_code_without_clues_is_rejected_like_a_wrong_one(self):
        state, (right,) = play([Action("enter_code", "door", code=SECRETS["door"])])
        _, (wrong,) = play([Action("enter_code", "door", code="0000")])
        self.assertFalse(state.escaped)
        self.assertEqual(right.kind, wrong.kind)
        self.assertEqual(right.message.replace(SECRETS["door"], "X"), wrong.message.replace("0000", "X"))

    def test_correct_drawer_code_before_reading_clues(self):
        state, (out,) = play([Action("enter_code", "drawer", code=SECRETS["drawer"])])
        self.assertFalse(out.ok)
        self.assertFalse(state.flags["drawer_unlocked"])

    def test_code_must_have_four_digits(self):
        _, (out,) = play([Action("enter_code", "drawer", code="12")])
        self.assertEqual(out.kind, "bad_code")

    def test_unknown_object(self):
        _, (out,) = play([Action("examine", None, raw_target="window")])
        self.assertEqual(out.kind, "unknown_object")
        self.assertIn("window", out.message)

    def test_hidden_compartment_unknown_until_found(self):
        _, (out,) = play([Action("examine", "compartment")])
        self.assertEqual(out.kind, "unknown_object")

    def test_index_card_needs_magnifying_glass(self):
        steps = SOLUTION[:4] + [Action("take", "index card"), Action("read", "index card")]
        state, outs = play(steps)
        self.assertEqual(outs[-1].kind, "too_small")
        self.assertNotIn("tiny_writing", state.solved)

    def test_key_does_not_open_door(self):
        state, outs = play(SOLUTION[:6] + [Action("use", "door", item="brass key")])
        self.assertFalse(outs[-1].ok)
        self.assertFalse(state.escaped)

    def test_cannot_pick_up_fixed_objects(self):
        _, (out,) = play([Action("take", "door")])
        self.assertEqual(out.kind, "not_takeable")

    def test_progress_is_remembered_over_many_turns(self):
        state, _ = play(SOLUTION[:5])
        for _ in range(50):
            apply(state, Action("examine", "bookshelf"))
        self.assertTrue(state.flags["drawer_unlocked"])
        self.assertIn("magnifying glass", state.inventory)
        self.assertEqual(state.solved, ["season_books"])

    def test_invariants_detect_contradictions(self):
        bad = GameState(inventory=["diary"])
        self.assertTrue(check_invariants(bad))
        bad = GameState()
        bad.flags["door_open"] = True
        self.assertTrue(check_invariants(bad))


if __name__ == "__main__":
    unittest.main()
