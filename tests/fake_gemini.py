"""A fake google-genai client for offline V2 tests.

Parsing requests (JSON mode) are answered from a dict of player message ->
parsed action; narration requests return a scripted text. Errors can be
injected to test retries and the fallback model.
"""

import json
from types import SimpleNamespace


class FakeAPIError(Exception):
    def __init__(self, code, message="error"):
        super().__init__(f"{code} {message}")
        self.code = code


def action(verb, target="none", item="none", code="", other_name=""):
    return {"verb": verb, "target": target, "item": item, "code": code, "other_name": other_name}


class FakeModels:
    def __init__(self, parses=None, narration="You do it.", errors=None):
        self.parses = parses or {}
        self.narration = narration
        self.errors = list(errors or [])  # exceptions raised by the first calls, in order
        self.calls = []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        if self.errors:
            err = self.errors.pop(0)
            if err is not None:
                raise err
        if getattr(config, "response_mime_type", None) == "application/json":
            message = contents.split("Player message: <<<", 1)[1].rsplit(">>>", 1)[0]
            parsed = self.parses.get(message, action("unknown"))
            return SimpleNamespace(text=json.dumps(parsed), parsed=None)
        text = self.narration(contents) if callable(self.narration) else self.narration
        return SimpleNamespace(text=text)

    @property
    def parse_calls(self):
        return [c for c in self.calls if getattr(c["config"], "response_mime_type", None) == "application/json"]

    @property
    def narration_calls(self):
        return [c for c in self.calls if getattr(c["config"], "response_mime_type", None) != "application/json"]


class FakeClient:
    def __init__(self, **kwargs):
        self.models = FakeModels(**kwargs)
