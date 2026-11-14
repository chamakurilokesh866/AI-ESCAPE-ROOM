"""Offline smoke tests for Version 1 (no API key or network needed).

Gemini is replaced by a fake client so the game loop and the Streamlit UI
can be checked without calling the real API.

Run:  python -m unittest discover -s tests -v
"""

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from v1 import game_master
from v1.prompts import ESCAPE_MARKER, build_system_prompt
from v1.room import ROOM

APP_PATH = str(Path(__file__).resolve().parent.parent / "v1" / "app.py")


class FakeModels:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        return SimpleNamespace(text=self.replies.pop(0))

    def generate_content_stream(self, model, contents, config):
        text = self.generate_content(model, contents, config).text
        return iter([SimpleNamespace(text=text[i:i + 5]) for i in range(0, len(text), 5)])


class FakeClient:
    def __init__(self, replies):
        self.models = FakeModels(replies)


class RoomDesignTests(unittest.TestCase):
    def test_room_meets_assignment_minimums(self):
        self.assertGreaterEqual(len(ROOM["objects"]), 5)
        self.assertGreaterEqual(len(ROOM["puzzles"]), 3)
        self.assertTrue(ROOM["final_challenge"])

    def test_system_prompt_contains_room_and_marker(self):
        prompt = build_system_prompt()
        for obj in ROOM["objects"]:
            self.assertIn(obj, prompt)
        self.assertIn(ESCAPE_MARKER, prompt)


class GameMasterTests(unittest.TestCase):
    def test_history_is_kept_between_turns(self):
        client = FakeClient(["You see a desk.", "You pick up the glass."])
        gm = game_master.GameMaster(client=client, model="test-model")
        gm.send("examine the desk")
        gm.send("take the magnifying glass")
        last_call = client.models.calls[-1]
        self.assertEqual(last_call["model"], "test-model")
        # user, model, user -> the whole conversation is sent each time
        self.assertEqual(len(last_call["contents"]), 3)
        self.assertEqual(len(gm.history), 4)
        self.assertFalse(gm.escaped)

    def test_escape_marker_ends_game_and_is_hidden(self):
        client = FakeClient([f"The door swings open!\n{ESCAPE_MARKER}"])
        gm = game_master.GameMaster(client=client)
        reply = gm.send("enter 1847 on the door")
        self.assertTrue(gm.escaped)
        self.assertNotIn(ESCAPE_MARKER, reply)

    def test_streaming_reply_and_fast_thinking(self):
        client = FakeClient([f"The door swings open!\n{ESCAPE_MARKER}"])
        gm = game_master.GameMaster(client=client, model="gemini-3.8-flash")
        chunks = list(gm.send_stream("enter 1847 on the door"))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(gm.escaped)
        self.assertEqual(gm.last_reply, "The door swings open!")
        self.assertEqual(len(gm.history), 2)
        thinking = client.models.calls[0]["config"].thinking_config
        self.assertEqual(thinking.thinking_level, game_master.types.ThinkingLevel.LOW)

    def test_model_name_from_env(self):
        with mock.patch.dict(os.environ, {"GEMINI_MODEL": "gemini-x"}):
            self.assertEqual(game_master.get_model_name(), "gemini-x")
        with mock.patch.dict(os.environ, {"GEMINI_MODEL": ""}):
            self.assertEqual(game_master.get_model_name(), game_master.DEFAULT_MODEL)

    def test_missing_key_raises_clear_error(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            with self.assertRaises(RuntimeError):
                game_master.make_client()


class StreamlitAppTests(unittest.TestCase):
    def setUp(self):
        from streamlit.testing.v1 import AppTest

        self.AppTest = AppTest

    def test_app_without_key_shows_error(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
            at = self.AppTest.from_file(APP_PATH).run()
        self.assertFalse(at.exception)
        self.assertIn("GEMINI_API_KEY", at.error[0].value)

    def test_full_playthrough_with_fake_gemini(self):
        fake = FakeClient(
            [
                "Four books stick out from the shelf.",
                f"The keypad turns green and the door opens. You are free!\n{ESCAPE_MARKER}",
            ]
        )
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}), mock.patch.object(
            game_master, "make_client", return_value=fake
        ):
            at = self.AppTest.from_file(APP_PATH).run()
            self.assertFalse(at.exception)
            at.chat_input[0].set_value("examine the bookshelf").run()
            self.assertIn("Four books", at.chat_message[-1].markdown[0].value)
            at.chat_input[0].set_value("enter 1847 on the door").run()
            self.assertFalse(at.exception)
            self.assertTrue(at.success, "escape banner should be shown")
            # Restart resets the conversation to the opening message only
            at.sidebar.button[0].click().run()
            self.assertEqual(len(at.session_state.messages), 1)


if __name__ == "__main__":
    unittest.main()
