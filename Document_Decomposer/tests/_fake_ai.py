import threading
from typing import Any


class SequencedFakeClient:
    """chat_json returns the next canned dict, in order. Thread-safe."""

    def __init__(self, responses: list[dict[str, Any]]):
        self._responses = list(responses)
        self._lock = threading.Lock()
        self.calls: list[tuple[list[dict], str]] = []

    def chat_json(self, messages: list[dict[str, str]], response_schema_hint: str) -> dict[str, Any]:
        with self._lock:
            self.calls.append((messages, response_schema_hint))
            if not self._responses:
                raise AssertionError("SequencedFakeClient ran out of canned responses")
            return self._responses.pop(0)
