"""Mechanical card-tag derivation from extracted elements (zero AI).

research_objects <- material facet; methods <- preparation+measurement+simulation.
Counts used-role occurrences per canonical entry; top_n display names, count desc
then alphabetical for stability. topic resolution: domain_tags -> registry topic
facet via find_by_surface only (unresolved are left for the bulk resolver, R6).

resolve_topics_bulk: library-wide domain_tags dedup → find_by_surface; unresolved
with client → AI batch judgment; remaining unresolved or client=None → create_entry.
Then writes classification.topic_ids per card.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .element_registry import (
    add_alias,
    create_entry,
    find_by_surface,
    load_registry,
    norm_key,
    resolve_id,
    save_registry,
)
from .element_matching import MATCH_SCHEMA_HINT, build_match_prompt
from .io_utils import write_json

METHOD_FACETS = ("preparation", "measurement", "simulation")


def derive_classification(
    elements_doc: dict, registry: dict,
    top_objects: int = 6, top_methods: int = 7,
) -> dict:
    """统计 used+canonical 的 material/方法类要素 → 卡片标签。

    排序规则(2026-06-10 抽样审计修正):
    1. **发现句主角优先**——名字(含别名)出现在本篇任一 finding surface 里的要素
       绝不被截掉(S43 的 propane 曾被截,而它正是"选择性序"发现的主角);
    2. 计数降序;
    3. **种子条目优先于自动条目**——顶层方法(MD/GCMC)多为种子词表,组件
       (力场/恒温器)多为自动建档;旧版平票按字典序,'Darkrim' 曾挤掉 GCMC;
    4. 名字字典序。
    """
    finding_text = " " + " ".join(
        norm_key(str(occ.get("surface") or ""))
        for occ in elements_doc.get("occurrences") or []
        if occ.get("facet") == "finding"
    ) + " "

    def in_finding(entry: dict) -> bool:
        for name in [entry["display_name"], *(entry.get("aliases") or [])]:
            key = norm_key(str(name))
            if key and f" {key} " in finding_text:
                return True
        return False

    mat: Counter = Counter()
    meth: Counter = Counter()
    entries_by_name: dict[str, dict] = {}
    for occ in elements_doc.get("occurrences") or []:
        if occ.get("role") != "used" or not occ.get("canonical_id"):
            continue
        eid = resolve_id(registry, occ["canonical_id"])
        entry = registry["entries"].get(eid)
        if not entry:
            continue
        entries_by_name.setdefault(entry["display_name"], entry)
        if entry["facet"] == "material":
            mat[entry["display_name"]] += 1
        elif entry["facet"] in METHOD_FACETS:
            meth[entry["display_name"]] += 1

    def top(counter: Counter, n: int) -> list[str]:
        def key(kv):
            name, count = kv
            entry = entries_by_name[name]
            return (
                not in_finding(entry),
                -count,
                entry.get("origin") != "seed",
                name,
            )
        return [name for name, _ in sorted(counter.items(), key=key)[:n]]

    return {"research_objects": top(mat, top_objects), "methods": top(meth, top_methods)}


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


def resolve_topics_bulk(
    library_dir: Path,
    registry_path: Path,
    log_path: Path,
    client=None,
) -> dict:
    """全库 domain_tags 去重 → find_by_surface; 未命中 → AI 批量判同或 create_entry;
    逐卡写 classification.topic_ids。

    Parameters
    ----------
    library_dir:
        Root library directory; scans library_dir/*/literature_card.json.
    registry_path:
        Path to registry.json (loaded and saved internally).
    log_path:
        Append-only registry event log.
    client:
        Optional AI client; if None, all unresolved tags create new entries.

    Returns
    -------
    dict with keys: tags_total, resolved_exact, resolved_ai, created,
    cards_updated, ai_calls.
    """
    library_dir = Path(library_dir)
    registry_path = Path(registry_path)
    log_path = Path(log_path)

    registry = load_registry(registry_path)

    # --- Phase 0: gather all domain_tags across library -----------------------
    card_paths: list[Path] = sorted(library_dir.glob("*/literature_card.json"))
    # map: normalised surface → original surface (first seen)
    all_surfaces: dict[str, str] = {}
    for cp in card_paths:
        card = json.loads(cp.read_text(encoding="utf-8"))
        for tag in (card.get("classification") or {}).get("domain_tags") or []:
            tag_s = str(tag).strip()
            norm = tag_s.lower()
            if norm and norm not in all_surfaces:
                all_surfaces[norm] = tag_s

    stats: dict[str, int] = {
        "tags_total": len(all_surfaces),
        "resolved_exact": 0,
        "resolved_ai": 0,
        "created": 0,
        "cards_updated": 0,
        "ai_calls": 0,
    }

    # --- Phase 1: find_by_surface for all unique surfaces --------------------
    surface_to_eid: dict[str, str] = {}  # norm → resolved eid
    unresolved_norms: list[str] = []

    for norm, original in all_surfaces.items():
        eid = find_by_surface(registry, "topic", original)
        if eid:
            surface_to_eid[norm] = eid
            stats["resolved_exact"] += 1
        else:
            unresolved_norms.append(norm)

    # --- Phase 2: AI batch (if client provided) ------------------------------
    if client is not None and unresolved_norms:
        unresolved_originals = [all_surfaces[n] for n in unresolved_norms]
        candidates = [
            e for e in registry["entries"].values()
            if e["facet"] == "topic" and not e.get("redirect_to")
        ]
        raw = client.chat_json(
            build_match_prompt("topic", unresolved_originals, candidates),
            MATCH_SCHEMA_HINT,
        )
        stats["ai_calls"] += 1

        ai_map: dict[str, str | None] = {}
        for m in (raw.get("matches") or []):
            if not isinstance(m, dict):
                continue
            surface_str = str(m.get("surface") or "")
            ai_map[surface_str] = m.get("element_id")

        still_unresolved: list[str] = []
        for norm in unresolved_norms:
            original = all_surfaces[norm]
            eid_proposed = ai_map.get(original)
            if eid_proposed and eid_proposed in registry["entries"]:
                eid_resolved = resolve_id(registry, eid_proposed)
                add_alias(registry, eid_resolved, original, "auto-stream", log_path)
                surface_to_eid[norm] = eid_resolved
                stats["resolved_ai"] += 1
            else:
                still_unresolved.append(norm)

        unresolved_norms = still_unresolved

    # --- Phase 2b: create entries for all remaining unresolved ---------------
    for norm in unresolved_norms:
        original = all_surfaces[norm]
        eid = create_entry(registry, "topic", original, "auto-stream", log_path)
        surface_to_eid[norm] = eid
        stats["created"] += 1

    # --- Phase 3: write topic_ids per card -----------------------------------
    for cp in card_paths:
        card = json.loads(cp.read_text(encoding="utf-8"))
        cls = card.get("classification") or {}
        domain_tags = cls.get("domain_tags")

        # Skip cards that have no domain_tags key at all
        if not domain_tags:
            continue

        topic_ids: list[str] = []
        seen: set[str] = set()
        for tag in domain_tags:
            norm = str(tag).strip().lower()
            eid = surface_to_eid.get(norm)
            if eid and eid not in seen:
                topic_ids.append(eid)
                seen.add(eid)

        existing_ids = cls.get("topic_ids")
        if existing_ids != topic_ids:
            card.setdefault("classification", {})["topic_ids"] = topic_ids
            write_json(cp, card)
            stats["cards_updated"] += 1

    save_registry(registry_path, registry)
    return stats
