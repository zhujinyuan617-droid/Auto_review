"""Derive vocabulary.json from the element registry (no AI).

Facet mapping:
  topic  ← registry topic entries
  method ← registry preparation + measurement + simulation entries
  object ← registry material entries

Non-redirect entries only.  Concepts sorted by canonical for determinism.
Members = sorted({display_name} ∪ set(aliases)).
raw_to_canonical[out_facet][member.lower()] = canonical; first-sorted-canonical
wins on collision, which is recorded in warnings.
"""
from __future__ import annotations

from .element_registry import norm_key

# Source facets that feed each OUTPUT facet
_FACET_SOURCES: dict[str, list[str]] = {
    "topic": ["topic"],
    "method": ["preparation", "measurement", "simulation"],
    "object": ["material"],
}


def derive_vocabulary(registry: dict, card_count: int) -> dict:
    """Build a vocabulary dict from registry entries.

    Parameters
    ----------
    registry:
        A loaded element registry dict (schema_version, entries, ...).
    card_count:
        Passed through to the output ``card_count`` field.

    Returns
    -------
    dict with keys: card_count, model, facets, raw_to_canonical, warnings.
    """
    facets_out: dict[str, dict] = {}
    raw_to_canonical: dict[str, dict[str, str]] = {}
    warnings: list[str] = []

    for out_facet, src_facets in _FACET_SOURCES.items():
        # Collect non-redirect entries for all source facets
        entries = [
            e for e in registry["entries"].values()
            if e["facet"] in src_facets and not e.get("redirect_to")
        ]
        # Sort: 人工锁定条目在别名冲突时优先胜出(策展不被自动条目覆盖); 次键按 display_name 保持确定性
        entries.sort(key=lambda e: (not e.get("human_locked", False), e["display_name"]))

        r2c: dict[str, str] = {}
        concepts: list[dict] = []

        for entry in entries:
            canonical = entry["display_name"]
            members = sorted({canonical} | set(entry.get("aliases") or []))
            concepts.append({"canonical": canonical, "members": members})
            for member in members:
                key = member.lower()
                if key in r2c:
                    if r2c[key] != canonical:
                        warnings.append(
                            f"collision: out_facet={out_facet!r} lower_member={key!r} "
                            f"kept={r2c[key]!r} ignored={canonical!r}"
                        )
                else:
                    r2c[key] = canonical

        facets_out[out_facet] = {"concepts": concepts}
        raw_to_canonical[out_facet] = r2c

    return {
        "card_count": card_count,
        "model": "derived-from-registry",
        "facets": facets_out,
        "raw_to_canonical": raw_to_canonical,
        "warnings": warnings,
    }
