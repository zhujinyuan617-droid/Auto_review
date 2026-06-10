"""Streaming match of one paper's element surfaces against the registry.

Pass 1: exact/alias (normalized). Pass 2 (optional, batched per facet): AI maps
each unresolved surface to an existing entry or null. Null -> create a new entry
(never force-fit). Proposed facets ("proposed:<name>") always create new entries.
"""
from __future__ import annotations

import json
from pathlib import Path

from .element_registry import add_alias, create_entry, find_by_surface, norm_key, resolve_id
from .io_utils import write_json

MATCH_SCHEMA_HINT = (
    'Return only one JSON object: {"matches": [{"surface": str, "element_id": str|null}]}. '
    "Do not wrap the JSON in Markdown."
)

_SYSTEM = (
    "You map raw research-element surface forms onto an existing registry of canonical "
    "elements for ONE facet. Map a surface to an element_id ONLY if they denote the same "
    "real-world thing (technique, material, quantity, topic, institution, or finding claim) "
    "(abbreviation, spelling or wording variant). If it is a "
    "genuinely different element, return null for it. Never guess."
)


def build_match_prompt(facet: str, surfaces: list[str], candidates: list[dict]) -> list[dict]:
    payload = {
        "facet": facet,
        "unresolved_surfaces": surfaces,
        "registry_candidates": [
            {"element_id": c["id"], "display_name": c["display_name"], "aliases": c["aliases"]}
            for c in candidates
        ],
    }
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def match_paper_elements(paper_dir: Path, registry: dict, client, log_path: Path) -> dict:
    path = paper_dir / "elements.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    stats = {"resolved_exact": 0, "resolved_ai": 0, "created": 0, "ai_calls": 0}

    unresolved: dict[str, list[str]] = {}
    for occ in data["occurrences"]:
        facet, surface = occ["facet"], occ["surface"]
        if facet.startswith("proposed:"):
            continue  # handled below as create
        eid = find_by_surface(registry, facet, surface)
        if eid:
            occ["canonical_id"] = eid
            stats["resolved_exact"] += 1
        else:
            unresolved.setdefault(facet, [])
            if surface not in unresolved[facet]:
                unresolved[facet].append(surface)

    ai_matched: dict[tuple[str, str], str | None] = {}
    if client is not None:
        for facet, surfaces in unresolved.items():
            candidates = [
                e for e in registry["entries"].values()
                if e["facet"] == facet and not e.get("redirect_to")
            ]
            raw = client.chat_json(build_match_prompt(facet, surfaces, candidates), MATCH_SCHEMA_HINT)
            stats["ai_calls"] += 1
            for m in (raw.get("matches") or []):
                if not isinstance(m, dict):
                    continue
                ai_matched[(facet, str(m.get("surface")))] = m.get("element_id")

    for occ in data["occurrences"]:
        if occ["canonical_id"] is not None:
            continue
        facet, surface = occ["facet"], occ["surface"]
        eid = ai_matched.get((facet, surface))
        if eid and eid in registry["entries"]:
            eid = resolve_id(registry, eid)
            add_alias(registry, eid, surface, "auto-stream", log_path)
            occ["canonical_id"] = eid
            stats["resolved_ai"] += 1
        else:
            existing = find_by_surface(registry, facet, surface)
            if existing:
                occ["canonical_id"] = existing
                stats["resolved_exact"] += 1
            else:
                new_id = create_entry(registry, facet, surface, "auto-stream", log_path)
                occ["canonical_id"] = new_id
                stats["created"] += 1

    write_json(path, data)
    return stats


# ---------------------------------------------------------------------------
# Bulk matching (SP-Speed): propose in parallel, commit serially.
# 设计:docs/superpowers/specs/2026-06-10-speed-sp-design.md
# ---------------------------------------------------------------------------


def _shortlist_candidates(registry: dict, facet: str, surface: str, cap: int = 8) -> list[dict]:
    """Same-facet, non-redirected entries ranked by norm_key token overlap.

    Zero-overlap entries are excluded — the AI judges against a SHORT list, never
    the whole facet (prompt size + anti-superbucket discipline).
    """
    tokens = set(norm_key(surface).split())
    if not tokens:
        return []
    scored: list[tuple[int, str, dict]] = []
    for entry in registry["entries"].values():
        if entry["facet"] != facet or entry.get("redirect_to"):
            continue
        names = [entry["display_name"], *entry["aliases"]]
        best = max((len(tokens & set(norm_key(n).split())) for n in names), default=0)
        if best > 0:
            scored.append((-best, entry["display_name"], entry))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [entry for _, _, entry in scored[:cap]]
