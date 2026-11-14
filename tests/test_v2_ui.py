"""Tests for the polished V2 UI: room cards, quick actions, examine buttons, win screen."""

import os
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from v2 import ui
from v2.room import SECRETS
from v2.state import GameState

APP = str(Path(__file__).resolve().parent.parent / "v2" / "app.py")
WALKTHROUGH = [
    "examine the desk", "take the note", "read the note", "examine the bookshelf",
    "enter 1111 on the drawer", "enter 5842 on the drawer", "take the magnifying glass",
    "take the brass key", "take the index card", "read the index card", "examine the painting",
    "use the brass key on the compartment", "take the diary", "read the diary",
    "enter 1847 on the door",
]


def offline_app() -> AppTest:
    return AppTest.from_file(APP).run()


class SceneTests(unittest.TestCase):
    def test_initial_cards(self):
        cards = {c["key"]: c for c in ui.scene_objects(GameState())}
        self.assertEqual(list(cards), ["desk", "bookshelf", "painting", "drawer", "door", "compartment"])
        self.assertEqual(cards["drawer"]["kind"], "locked")
        self.assertEqual(cards["door"]["kind"], "locked")
        self.assertEqual(cards["desk"]["kind"], "unexplored")
        self.assertEqual(cards["compartment"]["kind"], "hidden")
        self.assertFalse(cards["compartment"]["enabled"])
        self.assertEqual(cards["compartment"]["name"], "???")  # not revealed before it is found

    def test_cards_follow_state(self):
        s = GameState()
        s.flags.update(drawer_unlocked=True, compartment_found=True, compartment_open=True, door_open=True)
        cards = {c["key"]: c for c in ui.scene_objects(s)}
        self.assertEqual(cards["drawer"]["kind"], "unlocked")
        self.assertEqual(cards["compartment"]["kind"], "unlocked")
        self.assertEqual(cards["painting"]["kind"], "opened")
        self.assertEqual(cards["door"]["kind"], "opened")

    def test_ui_html_never_contains_codes(self):
        s = GameState()
        s.flags.update({k: True for k in s.flags})
        s.inventory = ["note", "diary"]
        html = "".join(ui.card_html(c) for c in ui.scene_objects(s)) + ui.inventory_html(s.inventory)
        for code in SECRETS.values():
            self.assertNotIn(code, html)

    def test_inventory_chips_escape_html(self):
        self.assertIn("&lt;b&gt;", ui.inventory_html(["<b>"]))
        self.assertIn("empty", ui.inventory_html([]))

    def test_fmt_duration(self):
        self.assertEqual(ui.fmt_duration(65), "01:05")
        self.assertEqual(ui.fmt_duration(3725), "1:02:05")


class AppUITests(unittest.TestCase):
    def setUp(self):
        # Offline for the whole test, even if a real key is in .env on this machine.
        patcher = mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_quick_action_buttons_send_commands(self):
        at = offline_app()
        at.button(key="qa_hint").click().run()
        self.assertFalse(at.exception)
        self.assertIn("Hint:", at.chat_message[-1].markdown[0].value)
        self.assertEqual(at.session_state.hints_used, 1)
        at.button(key="qa_inventory").click().run()
        self.assertIn("not carrying anything", at.chat_message[-1].markdown[0].value)

    def test_examine_button_on_room_card(self):
        at = offline_app()
        self.assertTrue(at.button(key="ex_compartment").disabled)  # hidden until found
        at.button(key="ex_painting").click().run()
        self.assertFalse(at.exception)
        self.assertTrue(at.session_state.game.state.flags["compartment_found"])
        self.assertFalse(at.button(key="ex_compartment").disabled)

    def test_full_playthrough_shows_win_screen(self):
        at = offline_app()
        for command in WALKTHROUGH:
            at.chat_input[0].set_value(command).run()
            self.assertFalse(at.exception, command)
        self.assertTrue(at.session_state.game.state.escaped)
        self.assertTrue(any("You escaped the library" in m.value for m in at.markdown))
        self.assertEqual(at.session_state.wrong_codes, 1)
        self.assertTrue(at.session_state.celebrated)
        self.assertTrue(at.button(key="qa_look").disabled)
        at.button(key="play_again").click().run()
        self.assertFalse(at.session_state.game.state.escaped)
        self.assertEqual(at.session_state.wrong_codes, 0)


if __name__ == "__main__":
    unittest.main()
