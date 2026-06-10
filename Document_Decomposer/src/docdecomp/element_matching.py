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


def collect_unresolved(
    paper_dirs: list[Path], registry: dict,
) -> tuple[dict[Path, dict], set[Path], list[dict]]:
    """Pass over papers' elements.json: resolve what a hash lookup can, gather the rest.

    Returns (docs, dirty, groups):
      docs   – elements.json path -> parsed doc (mutated in memory)
      dirty  – paths whose docs changed (exact hits / redirect re-points)
      groups – [{facet, surface, refs: [(path, occ_index)]}], deduped by (facet, norm_key)
    纯脚本、零 AI;悬空 canonical_id(指向不存在条目)按未解析收集 → 自愈。
    """
    index: dict[tuple[str, str], str] = {}
    for entry in registry["entries"].values():
        rid = resolve_id(registry, entry["id"])
        for name in [entry["display_name"], *entry["aliases"]]:
            index.setdefault((entry["facet"], norm_key(name)), rid)

    docs: dict[Path, dict] = {}
    dirty: set[Path] = set()
    groups: dict[tuple[str, str], dict] = {}
    for paper_dir in paper_dirs:
        path = paper_dir / "elements.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        docs[path] = doc
        for i, occ in enumerate(doc.get("occurrences") or []):
            cid = occ.get("canonical_id")
            if cid is not None and cid in registry["entries"]:
                rid = resolve_id(registry, cid)
                if rid != cid:
                    occ["canonical_id"] = rid
                    dirty.add(path)
                continue
            facet, surface = occ["facet"], occ["surface"]
            hit = index.get((facet, norm_key(surface)))
            if hit:
                occ["canonical_id"] = hit
                dirty.add(path)
                continue
            g = groups.setdefault(
                (facet, norm_key(surface)),
                {"facet": facet, "surface": surface, "refs": []},
            )
            g["refs"].append((path, i))
    return docs, dirty, list(groups.values())


def _pack_chunks(items: list[dict], chunk_size: int = 30, candidate_cap: int = 120) -> list[list[dict]]:
    """Greedy pack same-facet items: <=chunk_size surfaces AND <=candidate_cap union candidates (soft cap: a single oversized item gets its own chunk)."""
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    cur_ids: set[str] = set()
    for it in items:
        ids = {c["id"] for c in it["candidates"]}
        if cur and (len(cur) >= chunk_size or len(cur_ids | ids) > candidate_cap):
            chunks.append(cur)
            cur, cur_ids = [], set()
        cur.append(it)
        cur_ids |= ids
    if cur:
        chunks.append(cur)
    return chunks


def _judge_chunks(
    chunks_by_facet: dict[str, list[list[dict]]], client, parallel: int,
) -> tuple[dict[tuple[str, str], str | None], set[tuple[str, str]], int, int]:
    """Read-only parallel AI judging. Returns (verdicts, failed_keys, n_ok, n_failed).

    verdicts 以 (facet, norm_key(echoed surface)) 为键——组本身按 norm_key 去重,
    所以回显大小写差异不会错挂(同键即同组)。失败块的 surfaces 进 failed_keys,
    本轮跳过(宁可漏),下次重跑再试;绝不因 429/超时把整批拍成 create。
    n_ok/n_failed = 成功/失败的块数(= AI 调用计数)。
    candidate_cap 对单项超限是软上界(该项独占一块);
    BaseException(如 KeyboardInterrupt)故意不隔离、直接传播。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    jobs: list[tuple[str, list[dict]]] = []
    for facet, chunks in chunks_by_facet.items():
        for chunk in chunks:
            jobs.append((facet, chunk))

    verdicts: dict[tuple[str, str], str | None] = {}
    failed: set[tuple[str, str]] = set()
    n_ok = n_failed = 0
    if not jobs:
        return verdicts, failed, n_ok, n_failed

    def _run(job: tuple[str, list[dict]]) -> dict[tuple[str, str], str | None]:
        facet, chunk = job
        union: list[dict] = []
        seen: set[str] = set()
        for it in chunk:
            for c in it["candidates"]:
                if c["id"] not in seen:
                    seen.add(c["id"])
                    union.append(c)
        surfaces = [it["surface"] for it in chunk]
        raw = client.chat_json(build_match_prompt(facet, surfaces, union), MATCH_SCHEMA_HINT)
        out: dict[tuple[str, str], str | None] = {}
        for m in (raw.get("matches") or []):
            if isinstance(m, dict):
                out[(facet, norm_key(str(m.get("surface"))))] = m.get("element_id")
        return out

    with ThreadPoolExecutor(max_workers=max(1, min(parallel, len(jobs)))) as pool:
        fut_to_job = {pool.submit(_run, job): job for job in jobs}
        for fut in as_completed(fut_to_job):
            facet, chunk = fut_to_job[fut]
            try:
                verdicts.update(fut.result())
                n_ok += 1
            except Exception:  # noqa: BLE001 — 单块失败不扩散
                n_failed += 1
                for it in chunk:
                    failed.add((facet, norm_key(it["surface"])))
    return verdicts, failed, n_ok, n_failed


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
