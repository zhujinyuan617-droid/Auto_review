from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def _empty_graph() -> dict[str, Any]:
    # Fresh literals each call: a shared module constant would be poisoned if a
    # caller mutated the returned edges list / relation_counts dict.
    return {"edges": [], "relation_counts": {}, "n_edges": 0}


def load_edges(edges_path: Path) -> dict[str, Any]:
    """Read the engine's edges.json. Returns an empty graph if missing/malformed.

    The connection layer may not have run for the current library; the network
    view must degrade gracefully rather than error.
    """
    if not edges_path.is_file():
        return _empty_graph()
    try:
        data = json.loads(edges_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_graph()
    if not isinstance(data, dict):
        return _empty_graph()  # valid JSON but not an object (e.g. [], null, number)
    edges = data.get("edges")
    edges = edges if isinstance(edges, list) else []
    counts = data.get("relation_counts")
    return {
        "edges": edges,
        "relation_counts": counts if isinstance(counts, dict) else {},
        "n_edges": len(edges),
    }
