from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Protocol

USER_AGENT = "AutoReviewDesktop/0.1 (mailto:unknown@example.com)"


class Transport(Protocol):
    def get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        ...

    def get_bytes(self, url: str) -> bytes:
        ...


class UrllibTransport:
    """Real HTTP via stdlib urllib. Polite User-Agent; modest timeout."""

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout

    def get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        full = url
        if params:
            full = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_bytes(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()
