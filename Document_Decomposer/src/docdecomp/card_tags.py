"""Mechanical card-tag derivation from extracted elements (zero AI).

research_objects <- material facet; methods <- preparation+measurement+simulation.
Counts used-role occurrences per canonical entry; top_n display names, count desc
then alphabetical for stability. topic resolution: domain_tags -> registry topic
facet via find_by_surface only (unresolved are left for the bulk resolver, R6).
"""
from __future__ import annotations

from collections import Counter

from .element_registry import find_by_surface, resolve_id

METHOD_FACETS = ("preparation", "measurement", "simulation")


def derive_classification(elements_doc: dict, registry: dict, top_n: int = 5) -> dict:
    mat = Counter()
    meth = Counter()
    for occ in elements_doc.get("occurrences") or []:
        if occ.get("role") != "used" or not occ.get("canonical_id"):
            continue
        eid = resolve_id(registry, occ["canonical_id"])
        entry = registry["entries"].get(eid)
        if not entry:
            continue
        if entry["facet"] == "material":
            mat[entry["display_name"]] += 1
        elif entry["facet"] in METHOD_FACETS:
            meth[entry["display_name"]] += 1

    def top(counter: Counter) -> list[str]:
        return [name for name, _ in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]]

    return {"research_objects": top(mat), "methods": top(meth)}


def apply_derived_tags(card: dict, derived: dict) -> dict:
    cls = card.setdefault("classification", {})
    cls["research_objects"] = list(derived.get("research_objects") or [])
    cls["methods"] = list(derived.get("methods") or [])
    return card


def derive_topic_ids(card: dict, registry: dict) -> list[str]:
    out: list[str] = []
    for tag in (card.get("classification") or {}).get("domain_tags") or []:
        eid = find_by_surface(registry, "topic", str(tag))
        if eid and eid not in out:
            out.append(eid)
    return out
