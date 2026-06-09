from __future__ import annotations

from typing import Any


class FakeTransport:
    """Offline Transport: returns canned JSON/bytes keyed by url. Records calls."""

    def __init__(
        self,
        json_responses: dict[str, dict[str, Any]] | None = None,
        byte_responses: dict[str, bytes] | None = None,
    ):
        self._json = json_responses or {}
        self._bytes = byte_responses or {}
        self.json_calls: list[tuple[str, dict[str, str]]] = []
        self.byte_calls: list[str] = []

    def get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        self.json_calls.append((url, params))
        return self._json[url]

    def get_bytes(self, url: str) -> bytes:
        self.byte_calls.append(url)
        return self._bytes[url]
