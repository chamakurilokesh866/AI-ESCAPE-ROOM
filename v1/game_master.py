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

DEFAULT_MODEL = "gemini-3.5-flash-lite"


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


def fast_thinking_config(model: str) -> types.ThinkingConfig:
    """Minor speed patch (added with V2): use the model's lowest thinking level.

    gemini-3.8-flash thinks at MEDIUM by default, which made every V1 reply
    slow. LOW is its lowest level (MINIMAL is rejected); Gemini 2.x uses a
    thinking budget of 0 instead.
    """
    name = model.lower().removeprefix("models/")
    if name.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_budget=0)
    if "lite" in name or name.startswith(("gemini-3.6-flash", "gemini-3-flash", "gemini-3.5-flash")):
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)


@dataclass
class GameMaster:
    """Keeps the chat history and talks to Gemini."""

    client: genai.Client
    model: str = field(default_factory=get_model_name)
    system_prompt: str = field(default_factory=build_system_prompt)
    history: list[types.Content] = field(default_factory=list)
    escaped: bool = False

    use_fast_thinking: bool = True

    def _config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            system_instruction=self.system_prompt,
            temperature=0.8,
            thinking_config=fast_thinking_config(self.model) if self.use_fast_thinking else None,
        )

    def _call(self, method: str):
        """Call Gemini; if the model rejects the thinking setting, retry once without it."""
        try:
            return getattr(self.client.models, method)(
                model=self.model, contents=self.history, config=self._config())
        except Exception as exc:
            if self.use_fast_thinking and "thinking" in str(exc).lower():
                self.use_fast_thinking = False
                return getattr(self.client.models, method)(
                    model=self.model, contents=self.history, config=self._config())
            raise

    def _finish(self, reply: str) -> str:
        reply = reply.strip()
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

    def send(self, player_message: str) -> str:
        """Send the player's message, return the Game Master's reply."""
        self.history.append(
            types.Content(role="user", parts=[types.Part(text=player_message)])
        )
        response = self._call("generate_content")
        return self._finish(response.text or "")

    def send_stream(self, player_message: str):
        """Like ``send`` but yields the raw reply text chunk by chunk as it arrives.

        After the generator is exhausted, ``self.last_reply`` holds the cleaned
        reply (marker removed) and the history is updated.
        """
        self.history.append(
            types.Content(role="user", parts=[types.Part(text=player_message)])
        )
        parts: list[str] = []
        for chunk in self._call("generate_content_stream"):
            text = getattr(chunk, "text", None)
            if text:
                parts.append(text)
                yield text
        self.last_reply = self._finish("".join(parts))
