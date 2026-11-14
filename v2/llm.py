"""Thin wrapper around the google-genai client for Version 2."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-3.8-flash"


def get_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY", "").strip() or None


def get_model_name() -> str:
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def make_client(api_key: str | None = None):
    from google import genai

    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
    return genai.Client(api_key=key)


class LLM:
    """Calls one Gemini model."""

    def __init__(self, client, model: str | None = None):
        self.client = client
        self.model = model or get_model_name()
        self.last_model = None

    def generate(self, contents, config):
        response = self.client.models.generate_content(model=self.model, contents=contents, config=config)
        self.last_model = self.model
        return response
