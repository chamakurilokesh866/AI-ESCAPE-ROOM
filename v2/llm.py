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
* Slow replies with live Gemini. Every request uses the model's lowest
  thinking level, retries wait 0.5s/1s instead of 1s/2s/4s, a hung request
  times out after 30s, and ``generate_stream`` yields narration as it is
  written so the first words appear almost immediately.
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
        return max(0, int(os.getenv("GEMINI_MAX_RETRIES", "2")))
    except ValueError:
        return 2


# --------------------------------------------------------------- speed settings
# Latency problem found in live play: Gemini 3.x models "think" before they
# answer (gemini-3.8-flash defaults to thinking level MEDIUM). For a one-line
# JSON command or a 3-sentence description that hidden reasoning was most of
# the waiting time. We ask for the lowest thinking level each model supports.
REQUEST_TIMEOUT_MS = 30_000  # a hung request becomes a retryable network error


def get_thinking_mode() -> str:
    """GEMINI_THINKING: 'fast' (default, least thinking the model allows) or 'default'."""
    value = os.getenv("GEMINI_THINKING", "").strip().lower()
    return "default" if value in ("default", "model", "off", "none") else "fast"


def fast_thinking_config(model: str):
    """The lowest-latency thinking setting that ``model`` accepts.

    * Gemini 2.x: ``thinking_budget=0`` turns thinking off.
    * gemini-3.8-flash, gemini-3.7-flash, Gemini 4: lowest level is LOW
      (MINIMAL is rejected with 400).
    * Other Gemini 3.x Flash / Flash-Lite models: MINIMAL (near-off).
    """
    from google.genai import types

    name = model.lower().removeprefix("models/")
    if name.startswith("gemini-2"):
        return types.ThinkingConfig(thinking_budget=0)
    if name.startswith(("gemini-4", "gemini-3.8-flash", "gemini-3.7-flash")) or "pro" in name:
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)
    if "flash" in name:
        return types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL)
    return types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW)


def is_thinking_config_error(exc: Exception) -> bool:
    return error_code(exc) == 400 and "thinking" in str(exc).lower()


def make_client(api_key: str | None = None):
    from google import genai
    from google.genai import types

    key = api_key or get_api_key()
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
    return genai.Client(api_key=key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS))


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


class _Retry(Exception):
    """Internal signal: try the same model again (after an optional wait)."""


class _NextModel(Exception):
    """Internal signal: give up on this model and try the fallback."""


class LLM:
    """Calls Gemini with retries, exponential backoff and a fallback model.

    Speed: every request gets the model's fastest thinking setting (see
    ``fast_thinking_config``), and backoff waits are short (0.5s, 1s, ...) so a
    brief 503 costs about a second instead of several.
    """

    def __init__(self, client, model: str | None = None, fallback_model: str | None = "",
                 max_retries: int | None = None, base_delay: float = 0.5, max_delay: float = 4.0,
                 sleep=time.sleep, thinking: str | None = None):
        self.client = client
        self.model = model or get_model_name()
        self.fallback_model = get_fallback_model() if fallback_model == "" else fallback_model
        self.max_retries = get_max_retries() if max_retries is None else max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.sleep = sleep
        self.thinking = thinking or get_thinking_mode()
        self._no_thinking: set[str] = set()  # models that rejected our thinking setting
        self.last = CallStats()

    def _models(self) -> list[str]:
        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)
        return models

    def backoff(self, attempt: int) -> float:
        """Delay before retry number ``attempt`` (0-based): 0.5s, 1s, 2s... plus jitter."""
        delay = min(self.max_delay, self.base_delay * (2 ** attempt))
        return delay + random.uniform(0, delay * 0.25)

    def config_for(self, model: str, config):
        """Copy of ``config`` with the fast thinking setting for ``model``."""
        if (config is None or self.thinking != "fast" or model in self._no_thinking
                or getattr(config, "thinking_config", None) is not None):
            return config
        return config.model_copy(update={"thinking_config": fast_thinking_config(model)})

    def _handle_error(self, exc: Exception, model: str, attempt: int, stats: CallStats) -> None:
        """Classify a failed attempt: raise _Retry, _NextModel or a final LLMError."""
        code = error_code(exc)
        stats.errors.append(f"{model}: {code or type(exc).__name__}")
        if is_thinking_config_error(exc) and model not in self._no_thinking:
            self._no_thinking.add(model)  # model doesn't accept that level: use its default
            raise _Retry()
        if code in AUTH_CODES or code == 400:
            # Bad key or bad request: retrying or switching model won't help.
            raise LLMError(friendly_message(exc, model), exc) from exc
        if code in MODEL_MISSING_CODES:
            raise _NextModel()  # try the fallback model straight away
        if code in RETRYABLE_CODES or is_network_error(exc):
            if attempt < self.max_retries:
                self.sleep(self.backoff(attempt))
                raise _Retry()
            raise _NextModel()  # retries used up: move on to the fallback model
        raise LLMError(friendly_message(exc, model), exc) from exc

    def _run(self, call):
        """Run ``call(model, config_maker)`` with retries, backoff and the fallback model."""
        stats = CallStats()
        self.last = stats
        last_exc: Exception | None = None
        last_model = self.model
        for index, model in enumerate(self._models()):
            stats.fallback_used = index > 0
            last_model = model
            attempt = 0
            while attempt <= self.max_retries:
                stats.attempts += 1
                stats.model = model
                try:
                    return call(model)
                except Exception as exc:  # noqa: BLE001 - classified below
                    last_exc = exc
                    try:
                        self._handle_error(exc, model, attempt, stats)
                    except _Retry:
                        if not is_thinking_config_error(exc):
                            attempt += 1  # a thinking-setting retry doesn't use up an attempt
                        continue
                    except _NextModel:
                        break
        assert last_exc is not None
        raise LLMError(friendly_message(last_exc, last_model), last_exc) from last_exc

    def generate(self, contents, config):
        """One complete (non-streamed) response, used for the JSON intent parse."""
        return self._run(lambda model: self.client.models.generate_content(
            model=model, contents=contents, config=self.config_for(model, config)))

    def generate_stream(self, contents, config):
        """Yield the response text in chunks as Gemini produces it.

        Retries and the fallback model work as in ``generate`` until the first
        chunk arrives. After that, text is already on screen, so a failure
        mid-stream raises ``LLMError`` and the caller shows the engine's text.
        """
        def start(model):
            stream = iter(self.client.models.generate_content_stream(
                model=model, contents=contents, config=self.config_for(model, config)))
            return model, next(stream, None), stream

        model, first, stream = self._run(start)
        if first is not None and getattr(first, "text", None):
            yield first.text
        try:
            for chunk in stream:
                if getattr(chunk, "text", None):
                    yield chunk.text
        except Exception as exc:  # noqa: BLE001
            raise LLMError(friendly_message(exc, model), exc) from exc
