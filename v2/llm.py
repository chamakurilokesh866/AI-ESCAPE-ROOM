"""Reliable wrapper around the google-genai client for Version 2.

Problems seen with V1 in real use, and what this module does about them:

* ``404 NOT_FOUND`` - "models/gemini-2.5-flash is no longer available to new
  users". The model name is configurable, and a 404 makes us switch to the
  fallback model instead of failing.
* ``503 UNAVAILABLE`` - "This model is currently experiencing high demand".
  Temporary errors (429, 500, 502, 503, 504 and network errors) are retried
  with exponential backoff and jitter, then the fallback model is tried.
* Raw exception text shown to the player. Errors are turned into a short,
  clear ``LLMError.user_message``.
"""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_FALLBACK_MODEL = "gemini-flash-lite-latest"

RETRYABLE_CODES = {429, 500, 502, 503, 504}
MODEL_MISSING_CODES = {404}
AUTH_CODES = {401, 403}


PLACEHOLDER_KEYS = {"your-gemini-api-key-here", "changeme", "xxx"}


def get_api_key() -> str | None:
    """The key from the environment; the .env.example placeholder counts as missing."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    return None if not key or key.lower() in PLACEHOLDER_KEYS else key


def get_model_name() -> str:
    return os.getenv("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def get_fallback_model() -> str | None:
    """GEMINI_FALLBACK_MODEL; set it to 'none' to disable the fallback."""
    value = os.getenv("GEMINI_FALLBACK_MODEL")
    if value is None or not value.strip():
        return DEFAULT_FALLBACK_MODEL
    return None if value.strip().lower() in ("none", "off", "false") else value.strip()


def get_max_retries() -> int:
    try:
        return max(0, int(os.getenv("GEMINI_MAX_RETRIES", "3")))
    except ValueError:
        return 3


def make_client(api_key: str | None = None):
    from google import genai

    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
    return genai.Client(api_key=key)


class LLMError(RuntimeError):
    """A Gemini call failed for good. ``user_message`` is safe to show in the UI."""

    def __init__(self, user_message: str, cause: Exception | None = None):
        super().__init__(user_message)
        self.user_message = user_message
        self.cause = cause


def error_code(exc: Exception) -> int | None:
    code = getattr(exc, "code", None)
    if isinstance(code, int):
        return code
    status = getattr(exc, "status_code", None)
    return status if isinstance(status, int) else None


def is_network_error(exc: Exception) -> bool:
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return type(exc).__module__.startswith(("httpx", "httpcore", "requests", "urllib3"))


def friendly_message(exc: Exception, model: str) -> str:
    code = error_code(exc)
    if code in RETRYABLE_CODES - {429}:
        return f"Gemini is overloaded or temporarily unavailable ({code}). Please try again in a minute."
    if code == 429:
        return "Gemini rate limit reached (429). Wait a minute or check your free-tier quota."
    if code in MODEL_MISSING_CODES:
        return (f"The model '{model}' is not available for your API key (404). "
                "Set GEMINI_MODEL in .env to a model listed in Google AI Studio.")
    if code in AUTH_CODES or (code == 400 and "API key" in str(exc)):
        return "Gemini rejected the API key. Check GEMINI_API_KEY in your .env file."
    if is_network_error(exc):
        return "Could not connect to Gemini. Check your internet connection."
    return f"Gemini request failed ({type(exc).__name__}: {str(exc)[:120]})."


@dataclass
class CallStats:
    model: str | None = None
    attempts: int = 0
    fallback_used: bool = False
    errors: list[str] = field(default_factory=list)


class LLM:
    """Calls Gemini with retries, exponential backoff and a fallback model."""

    def __init__(self, client, model: str | None = None, fallback_model: str | None = "",
                 max_retries: int | None = None, base_delay: float = 1.0, max_delay: float = 8.0,
                 sleep=time.sleep):
        self.client = client
        self.model = model or get_model_name()
        self.fallback_model = get_fallback_model() if fallback_model == "" else fallback_model
        self.max_retries = get_max_retries() if max_retries is None else max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.sleep = sleep
        self.last = CallStats()

    def _models(self) -> list[str]:
        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)
        return models

    def backoff(self, attempt: int) -> float:
        """Delay before retry number ``attempt`` (0-based): 1s, 2s, 4s... plus jitter."""
        delay = min(self.max_delay, self.base_delay * (2 ** attempt))
        return delay + random.uniform(0, delay * 0.25)

    def generate(self, contents, config):
        stats = CallStats()
        self.last = stats
        last_exc: Exception | None = None
        last_model = self.model
        for index, model in enumerate(self._models()):
            stats.fallback_used = index > 0
            last_model = model
            for attempt in range(self.max_retries + 1):
                stats.attempts += 1
                stats.model = model
                try:
                    return self.client.models.generate_content(model=model, contents=contents, config=config)
                except Exception as exc:  # noqa: BLE001 - classified below
                    last_exc = exc
                    code = error_code(exc)
                    stats.errors.append(f"{model}: {code or type(exc).__name__}")
                    if code in AUTH_CODES or (code == 400):
                        # Bad key or bad request: retrying or switching model won't help.
                        raise LLMError(friendly_message(exc, model), exc) from exc
                    if code in MODEL_MISSING_CODES:
                        break  # try the fallback model straight away
                    if code in RETRYABLE_CODES or is_network_error(exc):
                        if attempt < self.max_retries:
                            self.sleep(self.backoff(attempt))
                            continue
                        break  # retries used up: move on to the fallback model
                    raise LLMError(friendly_message(exc, model), exc) from exc
        assert last_exc is not None
        raise LLMError(friendly_message(last_exc, last_model), last_exc) from last_exc
