"""Map service: lens payload composition + cache + arrivals + reading routes.

缓存文件 data/elements/map_layout_<lens>.json 是可重生产物(删了重算);
指纹不匹配→全量重算;论文只增且老篇要素未变→增量落位(老点冻结)。零 AI。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ..config import AppConfig
from .graph import (
    LENS_FACETS,
    element_names,
    idf,
    label_propagation,
    name_clusters,
    paper_features,
    similarity_edges,
)
from .layout import SCHEMA_VERSION, fingerprint, fr_layout, incremental_place

PARAMS = {"top_k": 10, "iters": 150, "seed": 42, "algo": "fr+lp-v1"}
ARRIVAL_BATCH_GAP_MIN = 30

ALL_LENSES = ["topic", "method", "material", "time", "institution"]


def _cache_path(config: AppConfig, lens: str) -> Path:
    return config.elements_data_dir / f"map_layout_{lens}.json"


def _all_paper_dirs(config: AppConfig) -> list[Path]:
    return sorted(p.parent for p in config.library_dir.glob("*/literature_card.json"))


def _load_card(paper_dir: Path) -> dict:
    try:
        return json.loads((paper_dir / "literature_card.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _degree_sizes(nodes: list[str], edges: list[tuple[str, str, float]]) -> dict[str, float]:
    deg = {n: 0.0 for n in nodes}
    for a, b, w in edges:
        if a in deg:
            deg[a] += w
        if b in deg:
            deg[b] += w
    return deg


def _element_lens_payload(config: AppConfig, lens: str, force: bool = False) -> dict:
    feats = paper_features(config.elements_db, config.library_dir, lens)
    all_ids = [p.name for p in _all_paper_dirs(config)]
    for pid in all_ids:
        feats.setdefault(pid, set())
    fp = fingerprint(lens, feats, PARAMS)

    cache_path = _cache_path(config, lens)
    cache = None
    if not force and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cache = None
    if cache and cache.get("fingerprint") == fp:
        return cache

    edges = similarity_edges(feats, idf(feats), top_k=PARAMS["top_k"])
    sizes = _degree_sizes(list(feats), edges)
    names = element_names(config.elements_db) if config.elements_db.exists() else {}

    incremental = None
    if cache and not force and cache.get("params") == PARAMS:
        cached_ids = {n["id"] for n in cache.get("nodes") or []}
        if cached_ids and cached_ids < set(feats):
            old_subset = {pid: feats[pid] for pid in cached_ids}
            if fingerprint(lens, old_subset, PARAMS) == cache.get("fingerprint_papers", ""):
                incremental = cache

    if incremental:
        old_pos = {n["id"]: (n["x"], n["y"]) for n in incremental["nodes"]}
        old_cluster = {n["id"]: n["cluster"] for n in incremental["nodes"]}
        new_ids = sorted(set(feats) - set(old_pos))
        nb_map: dict[str, list[tuple[str, float]]] = {pid: [] for pid in new_ids}
        for a, b, w in edges:
            if a in nb_map and b in old_pos:
                nb_map[a].append((b, w))
            elif b in nb_map and a in old_pos:
                nb_map[b].append((a, w))
        for pid in nb_map:
            nb_map[pid].sort(key=lambda t: (-t[1], t[0]))
        new_pos = incremental_place(old_pos, nb_map)
        pos = {**old_pos, **new_pos}
        clusters_map = dict(old_cluster)
        for pid in new_ids:
            clusters_map[pid] = old_cluster.get(nb_map[pid][0][0]) if nb_map[pid] else pid
        labels = clusters_map
    else:
        labels = label_propagation(sorted(feats), edges)
        pos = fr_layout(sorted(feats), edges, labels, iters=PARAMS["iters"], seed=PARAMS["seed"])

    cluster_labels = name_clusters(labels, feats, idf(feats), names)
    nodes_out = [
        {
            "id": pid,
            "x": round(pos.get(pid, (0.5, 0.5))[0], 4),
            "y": round(pos.get(pid, (0.5, 0.5))[1], 4),
            "cluster": labels.get(pid, pid),
            "size": round(sizes.get(pid, 0.0), 3),
            "lit": bool(feats.get(pid)),
        }
        for pid in sorted(feats)
    ]
    cluster_counts: dict[str, int] = {}
    for n in nodes_out:
        cluster_counts[n["cluster"]] = cluster_counts.get(n["cluster"], 0) + 1
    payload = {
        "schema_version": SCHEMA_VERSION,
        "lens": lens,
        "lenses": ALL_LENSES,
        "fingerprint": fp,
        "fingerprint_papers": fp,
        "params": PARAMS,
        "nodes": nodes_out,
        "clusters": [
            {"id": c, "label": cluster_labels.get(c, c), "n": cluster_counts[c]}
            for c in sorted(cluster_counts)
        ],
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _time_lens_payload(config: AppConfig) -> dict:
    nodes = []
    for paper_dir in _all_paper_dirs(config):
        card = _load_card(paper_dir)
        year = (card.get("paper") or {}).get("year")
        try:
            year = int(year) if year is not None else None
        except (TypeError, ValueError):
            year = None
        nodes.append({"id": paper_dir.name, "year": year, "lit": year is not None})
    return {"schema_version": SCHEMA_VERSION, "lens": "time", "lenses": ALL_LENSES, "nodes": nodes}


def _institution_lens_payload(config: AppConfig) -> dict:
    """机构镜头:每篇归到出现最多的机构;仅 1 篇的机构归「其他」区。"""
    inst_papers: dict[str, list[str]] = {}
    paper_insts: dict[str, list[str]] = {}
    for paper_dir in _all_paper_dirs(config):
        path = paper_dir / "authorship.json"
        insts: list[str] = []
        if path.exists():
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                ids = list(doc.get("institution_ids") or [])
                for a in doc.get("authors") or []:
                    ids.extend(a.get("institution_ids") or [])
                seen: dict[str, None] = {}
                for i in ids:
                    seen.setdefault(i, None)
                insts = list(seen)
            except (OSError, ValueError):
                insts = []
        paper_insts[paper_dir.name] = insts
        for i in insts:
            inst_papers.setdefault(i, []).append(paper_dir.name)

    multi = {i for i, ps in inst_papers.items() if len(ps) > 1}

    def _primary(insts: list[str]) -> str:
        cands = [i for i in insts if i in multi]
        if not cands:
            return "__other__"
        return sorted(cands, key=lambda i: (-len(inst_papers[i]), i))[0]

    labels = {pid: _primary(insts) for pid, insts in paper_insts.items()}
    edges = []
    for i in sorted(multi):
        ps = sorted(inst_papers[i])
        for a_idx, a in enumerate(ps):
            for b in ps[a_idx + 1:]:
                edges.append((a, b, 1.0))
    pos = fr_layout(sorted(paper_insts), edges, labels, iters=PARAMS["iters"], seed=PARAMS["seed"])

    inst_names = _institution_names(config)
    nodes = [
        {"id": pid, "x": round(pos[pid][0], 4), "y": round(pos[pid][1], 4),
         "cluster": labels[pid], "size": float(len(paper_insts[pid])),
         "lit": bool(paper_insts[pid])}
        for pid in sorted(paper_insts)
    ]
    counts: dict[str, int] = {}
    for n in nodes:
        counts[n["cluster"]] = counts.get(n["cluster"], 0) + 1
    clusters = [
        {"id": c, "label": ("其他(孤篇机构)" if c == "__other__" else inst_names.get(c, c.rsplit("/", 1)[-1])),
         "n": counts[c]}
        for c in sorted(counts)
    ]
    return {"schema_version": SCHEMA_VERSION, "lens": "institution", "lenses": ALL_LENSES,
            "nodes": nodes, "clusters": clusters}


def _institution_names(config: AppConfig) -> dict[str, str]:
    try:
        reg = json.loads(config.institutions_registry_path.read_text(encoding="utf-8"))
        return {e["id"]: e["display_name"] for e in (reg.get("entries") or {}).values()}
    except (OSError, ValueError):
        return {}


def lens_payload(config: AppConfig, lens: str, force: bool = False) -> dict:
    if lens in LENS_FACETS:
        return _element_lens_payload(config, lens, force=force)
    if lens == "time":
        return _time_lens_payload(config)
    if lens == "institution":
        return _institution_lens_payload(config)
    raise ValueError(f"unknown lens: {lens}")


def relayout(config: AppConfig, lens: str) -> dict:
    path = _cache_path(config, lens)
    if path.exists():
        path.unlink()
    return lens_payload(config, lens, force=True)


def arrivals(config: AppConfig) -> dict:
    """最近导入批次 = 卡片 mtime 相邻间隔 ≤30 分钟的最新一组(mtime 启发式,importer
    落 batch 标记后替换);每篇附 topic 镜头 top-3 最近邻与所落区。"""
    dirs = _all_paper_dirs(config)
    stamped = sorted(
        ((p, (p / "literature_card.json").stat().st_mtime) for p in dirs),
        key=lambda t: -t[1],
    )
    batch: list[str] = []
    prev = None
    for paper_dir, ts in stamped:
        if prev is not None and (prev - ts) > ARRIVAL_BATCH_GAP_MIN * 60:
            break
        batch.append(paper_dir.name)
        prev = ts
    if len(batch) == len(stamped):
        # 整库一个批次 = 没有"新着陆"可言(首建库),回空
        return {"batch": [], "note": "library built in one batch"}

    feats = paper_features(config.elements_db, config.library_dir, "topic")
    weights = idf(feats)
    topic_cache = lens_payload(config, "topic")
    cluster_of = {n["id"]: n["cluster"] for n in topic_cache["nodes"]}
    cluster_label = {c["id"]: c["label"] for c in topic_cache["clusters"]}

    out = []
    batch_set = set(batch)
    for pid in batch:
        scores: dict[str, float] = {}
        mine = feats.get(pid, set())
        for other, elems in feats.items():
            if other == pid or other in batch_set:
                continue
            s = sum(weights.get(e, 0.0) for e in mine & elems)
            if s > 0:
                scores[other] = s
        top = sorted(scores.items(), key=lambda t: (-t[1], t[0]))[:3]
        cluster = cluster_of.get(pid, "")
        out.append({
            "paper_id": pid,
            "cluster": cluster,
            "cluster_label": cluster_label.get(cluster, ""),
            "neighbors": [{"paper_id": n, "score": round(s, 3)} for n, s in top],
            "isolated": not top,
        })
    return {"batch": out, "gap_minutes": ARRIVAL_BATCH_GAP_MIN}


def route(config: AppConfig, lens: str, cluster: str) -> dict:
    """区内阅读路线:综述优先(paper.paper_type 含 review,字段缺省则该规则不生效)→ 核心度降序。"""
    payload = lens_payload(config, lens)
    members = [n for n in payload.get("nodes") or [] if n.get("cluster") == cluster]

    def _is_review(pid: str) -> bool:
        card = _load_card(config.library_dir / pid)
        ptype = (card.get("paper") or {}).get("paper_type") or ""
        return "review" in str(ptype).lower()

    ordered = sorted(members, key=lambda n: (not _is_review(n["id"]), -n.get("size", 0.0), n["id"]))
    return {
        "lens": lens,
        "cluster": cluster,
        "order": [n["id"] for n in ordered],
        "start_with": [n["id"] for n in ordered[:3]],
        "hint": "建议从这 3 篇入手(综述优先,其次按与同区文献的关联紧密度)",
    }
