from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import engine_bridge

engine_bridge.ensure_engine_use_on_path()  # adds Document_Decomposer/scripts/use to sys.path

import propose_angles as _angles  # engine module (now importable)  # noqa: E402


def _empty_angles() -> dict[str, Any]:
    # Fresh literals each call: a shared constant would be poisoned if a caller
    # mutated the returned tension/gaps/synthesis lists.
    return {"tension": [], "gaps": [], "synthesis": []}


def propose_candidate_angles(edges: list[dict[str, Any]], cidx: dict[str, Any]) -> dict[str, Any]:
    """Deterministic candidate writing angles from the relation graph + concept index."""
    return _angles.build_candidates(edges, cidx)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_angles(edges_path: Path, concept_index_path: Path) -> dict[str, Any]:
    """Load edges.json + concept_index.json and build candidate angles.

    Missing/malformed inputs degrade to an empty candidate set (no error) — the
    connection layer may not have run for the current library.
    """
    edges_doc = _read_json(edges_path)
    cidx = _read_json(concept_index_path)
    edges = (edges_doc.get("edges") if isinstance(edges_doc, dict) else None) or []
    if not isinstance(cidx, dict):
        cidx = {}
    if not edges and not cidx:
        return _empty_angles()
    return propose_candidate_angles(edges, cidx)
