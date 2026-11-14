"""Gemini-powered Game Master for Version 1.

V1 design: the whole conversation is sent to Gemini on every turn together
with a system prompt describing the room. The LLM decides what happens,
remembers progress (via the chat history) and signals the end of the game
by writing ESCAPE_MARKER.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv
from google import genai
from google.genai import types

from v1.prompts import ESCAPE_MARKER, build_system_prompt

load_dotenv()

DEFAULT_MODEL = "gemini-2.5-flash"


def get_model_name() -> str:
    return os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL


def get_api_key() -> str | None:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return key or None


def make_client(api_key: str | None = None) -> genai.Client:
    key = api_key or get_api_key()
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Copy .env.example to .env and add your key."
        )
    return genai.Client(api_key=key)


@dataclass
class GameMaster:
    """Keeps the chat history and talks to Gemini."""

    client: genai.Client
    model: str = field(default_factory=get_model_name)
    system_prompt: str = field(default_factory=build_system_prompt)
    history: list[types.Content] = field(default_factory=list)
    escaped: bool = False

    def send(self, player_message: str) -> str:
        """Send the player's message, return the Game Master's reply."""
        self.history.append(
            types.Content(role="user", parts=[types.Part(text=player_message)])
        )
        response = self.client.models.generate_content(
            model=self.model,
            contents=self.history,
            config=types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                temperature=0.8,
            ),
        )
        reply = (response.text or "").strip()
        if not reply:
            reply = "The room is silent... (the Game Master did not respond, try again)"

        # Keep the raw reply (with marker) in history so the model stays consistent.
        self.history.append(
            types.Content(role="model", parts=[types.Part(text=reply)])
        )

        if ESCAPE_MARKER in reply:
            self.escaped = True
            reply = reply.replace(ESCAPE_MARKER, "").strip()
        return reply
