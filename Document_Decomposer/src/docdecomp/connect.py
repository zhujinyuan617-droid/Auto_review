"""Shared helpers for the connection layer (architecture v2).

Currently minimal (deferral list). Phase 5 will move more shared logic here so each
CLI script stays a thin "parse args -> call one function -> write one artifact".
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # .../Document_Decomposer
DEFERRED_PATH = ROOT / "reports" / "connection" / "deferred.json"


def load_deferred() -> set[str]:
    """Paper ids excluded from the connection layer (non-English / off-topic / non-article).
    Edit reports/connection/deferred.json to change. Missing file -> nothing deferred."""
    try:
        return set(json.loads(DEFERRED_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return set()
