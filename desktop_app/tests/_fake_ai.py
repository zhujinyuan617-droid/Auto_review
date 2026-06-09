from __future__ import annotations

from typing import Any


class SequencedFakeClient:
    """A stand-in AI client: chat_json returns the next canned dict, in order.

    The AI pipeline calls chat_json once per stage (sections, reading, card), so
    a list of three canned dicts drives a full offline run.
    """

    def __init__(self, responses: list[dict[str, Any]]):
        self._responses = list(responses)
        self._calls: list[tuple[list[dict], str]] = []

    def chat_json(self, messages: list[dict[str, str]], response_schema_hint: str) -> dict[str, Any]:
        self._calls.append((messages, response_schema_hint))
        if not self._responses:
            raise AssertionError("SequencedFakeClient ran out of canned responses")
        return self._responses.pop(0)

    @property
    def call_count(self) -> int:
        return len(self._calls)
