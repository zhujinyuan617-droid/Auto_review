"""One-time bootstrap consolidation: all extracted surfaces -> registry v1.

Per facet, surfaces (with counts) go to the AI in chunks; existing canonical names
(seeds + earlier chunks) are shown so later chunks attach instead of duplicating.
Anti-superbucket discipline (ISSUES I12): groups capped at 8 members in-prompt and
audited mechanically afterwards. Every surface MUST end up assigned: leftovers get
their own entries (never force-fit, never silently dropped). After consolidation,
all papers' occurrences are assigned via exact/alias matching only (no AI).
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .element_matching import match_paper_elements
from .element_registry import (
    add_alias,
    create_entry,
    find_by_surface,
    new_registry_from_seeds,
    save_registry,
)

CONSOLIDATE_SCHEMA_HINT = (
    'Return only one JSON object: {"groups": [{"canonical": str, "members": [str, ...]}]}. '
    "Do not wrap the JSON in Markdown."
)

_SYSTEM = (
    "You consolidate raw research-element surface forms into canonical groups for ONE facet.\n"
    "Rules:\n"
    "1. Group ONLY true same-thing variants (abbreviation, spelling, plural, word order). "
    "Different techniques/materials/quantities must stay separate.\n"
    "2. A group has at most 8 members. No catch-all groups like 'other methods'.\n"
    "3. canonical = the most common full English name. If a surface matches one of the "
    "existing canonical names provided, use exactly that existing name as the group's canonical.\n"
    "4. Every input surface must appear in exactly one group; a group of one is fine.\n"
    "5. Output strictly the JSON schema; no Markdown."
)

CHUNK_SIZE = 150


def collect_surfaces(library_dir: Path) -> dict[str, Counter]:
    counts: dict[str, Counter] = {}
    for elements_path in sorted(Path(library_dir).glob("*/elements.json")):
        data = json.loads(elements_path.read_text(encoding="utf-8"))
        for occ in data.get("occurrences") or []:
            counts.setdefault(occ["facet"], Counter())[occ["surface"]] += 1
    return counts


def build_consolidation_prompt(facet: str, surface_counts: list[tuple[str, int]],
                               existing_canonicals: list[str]) -> list[dict]:
    payload = {
        "facet": facet,
        "existing_canonical_names": existing_canonicals,
        "surfaces": [{"surface": s, "papers": n} for s, n in surface_counts],
    }
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def bootstrap_registry(library_dir: Path, seeds: dict, client, data_dir: Path,
                       chunk_size: int = CHUNK_SIZE, progress=lambda m: None) -> dict:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    log_path = data_dir / "registry_log.jsonl"
    registry = new_registry_from_seeds(seeds)

    for facet, counter in sorted(collect_surfaces(library_dir).items()):
        surfaces = counter.most_common()
        for start in range(0, len(surfaces), chunk_size):
            chunk = surfaces[start:start + chunk_size]
            existing = sorted(
                e["display_name"] for e in registry["entries"].values()
                if e["facet"] == facet and not e.get("redirect_to")
            )
            progress(f"consolidating {facet}: {start + len(chunk)}/{len(surfaces)}")
            raw = client.chat_json(
                build_consolidation_prompt(facet, chunk, existing), CONSOLIDATE_SCHEMA_HINT
            )
            assigned: set[str] = set()
            for group in raw.get("groups") or []:
                if not isinstance(group, dict):
                    continue
                canonical = str(group.get("canonical") or "").strip()
                members = [str(m).strip() for m in (group.get("members") or []) if str(m).strip()]
                if not canonical or not members:
                    continue
                eid = find_by_surface(registry, facet, canonical) or create_entry(
                    registry, facet, canonical, "bootstrap", log_path
                )
                for member in members[:8]:  # in-prompt cap, enforced mechanically too
                    add_alias(registry, eid, member, "bootstrap", log_path)
                    assigned.add(member)
            for surface, _ in chunk:  # leftovers: own entries, never dropped
                if surface not in assigned and not find_by_surface(registry, facet, surface):
                    create_entry(registry, facet, surface, "bootstrap", log_path)

    for elements_path in sorted(Path(library_dir).glob("*/elements.json")):
        match_paper_elements(elements_path.parent, registry, None, log_path)

    save_registry(data_dir / "registry.json", registry)
    return registry


def superbucket_report(registry: dict, max_aliases: int = 12) -> list[dict]:
    flagged = []
    for entry in registry["entries"].values():
        if len(entry.get("aliases") or []) > max_aliases:
            flagged.append({"id": entry["id"], "facet": entry["facet"],
                            "display_name": entry["display_name"],
                            "alias_count": len(entry["aliases"])})
    return sorted(flagged, key=lambda x: -x["alias_count"])
