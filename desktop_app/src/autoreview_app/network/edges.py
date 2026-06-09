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
    edges = data.get("edges") or []
    return {
        "edges": edges,
        "relation_counts": data.get("relation_counts") or {},
        "n_edges": len(edges),
    }
