"""Map service: lens payload composition + cache + arrivals + reading routes.

缓存文件 data/elements/map_layout_<lens>.json 是可重生产物(删了重算);
指纹不匹配→全量重算;论文只增且老篇要素未变→增量落位(老点冻结)。
除"区描述句"(Wave2,显式调用、按成员哈希缓存)外零 AI。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
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
from .layout import SCHEMA_VERSION, fingerprint, fr_layout, incremental_place, spread_clusters

PARAMS = {"top_k": 10, "iters": 150, "seed": 42, "algo": "fr+lp-v2"}  # v2: 区级分离后处理
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
        labels = _merge_tiny_clusters(labels, edges, min_size=3)
        pos = fr_layout(sorted(feats), edges, labels, iters=PARAMS["iters"], seed=PARAMS["seed"])
        pos = spread_clusters(pos, labels)

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
            {"id": c,
             "label": "零散文献" if c == "__misc__" else cluster_labels.get(c, c),
             "n": cluster_counts[c],
             **({"misc": True} if c == "__misc__" else {})}
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


def _paper_institutions(paper_dir: Path) -> list[str]:
    path = paper_dir / "authorship.json"
    if not path.exists():
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    ids = list(doc.get("institution_ids") or [])
    for a in doc.get("authors") or []:
        ids.extend(a.get("institution_ids") or [])
    seen: dict[str, None] = {}
    for i in ids:
        seen.setdefault(i, None)
    return list(seen)


def _institution_lens_payload(config: AppConfig) -> dict:
    """机构镜头:每篇归到出现最多的机构;仅 1 篇的机构归「其他」区。"""
    inst_papers: dict[str, list[str]] = {}
    paper_insts: dict[str, list[str]] = {}
    for paper_dir in _all_paper_dirs(config):
        insts = _paper_institutions(paper_dir)
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
    pos = spread_clusters(pos, labels)

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


def _generic_cache(config: AppConfig, lens: str, feats_like: dict[str, set[str]],
                   build, force: bool = False) -> dict:
    """time/institution 镜头的缓存壳:指纹=镜头数据快照;不匹配才重建。"""
    fp = fingerprint(lens, feats_like, {"algo": PARAMS["algo"]})
    path = _cache_path(config, lens)
    if not force and path.exists():
        try:
            cache = json.loads(path.read_text(encoding="utf-8"))
            if cache.get("fingerprint") == fp:
                return cache
        except (OSError, ValueError):
            pass
    payload = build()
    payload["fingerprint"] = fp
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def lens_payload(config: AppConfig, lens: str, force: bool = False) -> dict:
    if lens in LENS_FACETS:
        payload = _element_lens_payload(config, lens, force=force)
    elif lens == "time":
        feats_like = {}
        for paper_dir in _all_paper_dirs(config):
            year = (_load_card(paper_dir).get("paper") or {}).get("year")
            feats_like[paper_dir.name] = {f"y:{year}"}
        payload = _generic_cache(config, lens, feats_like,
                                 lambda: _time_lens_payload(config), force=force)
    elif lens == "institution":
        feats_like = {}
        for paper_dir in _all_paper_dirs(config):
            feats_like[paper_dir.name] = set(_paper_institutions(paper_dir))
        payload = _generic_cache(config, lens, feats_like,
                                 lambda: _institution_lens_payload(config), force=force)
    else:
        raise ValueError(f"unknown lens: {lens}")
    if payload.get("clusters"):
        payload = _apply_meta(config, lens, payload)
    return payload


def relayout(config: AppConfig, lens: str) -> dict:
    path = _cache_path(config, lens)
    if path.exists():
        path.unlink()
    return lens_payload(config, lens, force=True)


def _batches_path(config: AppConfig) -> Path:
    return config.elements_data_dir / "import_batches.jsonl"


def record_import_batch(config: AppConfig, batch_id: str, paper_id: str) -> None:
    """导入成功后登记真实批次(api 层在 runner 成功返回处调用)。"""
    path = _batches_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {"batch_id": batch_id, "paper_id": paper_id,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def _latest_marked_batch(config: AppConfig) -> list[str]:
    path = _batches_path(config)
    if not path.exists():
        return []
    last_id = None
    papers: list[str] = []
    try:
        for raw in path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            rec = json.loads(raw)
            if rec.get("batch_id") != last_id:
                last_id = rec.get("batch_id")
                papers = []
            pid = rec.get("paper_id")
            if pid and (config.library_dir / pid / "literature_card.json").exists():
                papers.append(pid)
    except (OSError, ValueError):
        return []
    return papers


def arrivals(config: AppConfig) -> dict:
    """最近导入批次:优先读 importer 落的真实批次标记(import_batches.jsonl);
    无标记时降级为卡片 mtime 相邻 ≤30 分钟启发式。每篇附 topic top-3 最近邻与所落区。"""
    dirs = _all_paper_dirs(config)
    batch = _latest_marked_batch(config)
    if not batch:
        stamped = sorted(
            ((p, (p / "literature_card.json").stat().st_mtime) for p in dirs),
            key=lambda t: -t[1],
        )
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


# ---------------------------------------------------------------------------
# Wave 2:小区合并 / 区元数据(人工区名+AI 区描述)/ 真邻居 / 首现 / 机构×要素
# ---------------------------------------------------------------------------


def _merge_tiny_clusters(labels: dict[str, str], edges: list[tuple[str, str, float]],
                         min_size: int = 3) -> dict[str, str]:
    """<min_size 的区并入"与其成员边权和最大"的达标区;无任何边的并入 __misc__。确定性。"""
    sizes: dict[str, int] = {}
    for c in labels.values():
        sizes[c] = sizes.get(c, 0) + 1
    big = {c for c, n in sizes.items() if n >= min_size}
    if not big:
        return labels  # 没有达标区(极小库):保持原样,不强造 misc
    out = dict(labels)
    tiny = sorted(c for c, n in sizes.items() if n < min_size)
    for c in tiny:
        members = sorted(n for n, lab in labels.items() if lab == c)
        weight_to: dict[str, float] = {}
        for a, b, w in edges:
            la, lb = labels.get(a), labels.get(b)
            if la == c and lb in big:
                weight_to[lb] = weight_to.get(lb, 0.0) + w
            elif lb == c and la in big:
                weight_to[la] = weight_to.get(la, 0.0) + w
        if weight_to:
            target = sorted(weight_to.items(), key=lambda t: (-t[1], t[0]))[0][0]
        else:
            target = "__misc__"
        for m in members:
            out[m] = target
    return out


def _meta_path(config: AppConfig, lens: str) -> Path:
    return config.elements_data_dir / f"map_meta_{lens}.json"


def _members_key(members: list[str]) -> str:
    return hashlib.sha256("|".join(sorted(members)).encode("utf-8")).hexdigest()[:16]


def _load_meta(config: AppConfig, lens: str) -> dict:
    path = _meta_path(config, lens)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_meta(config: AppConfig, lens: str, meta: dict) -> None:
    path = _meta_path(config, lens)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if (a or b) else 0.0


def _apply_meta(config: AppConfig, lens: str, payload: dict) -> dict:
    """把人工区名(精确键或成员 Jaccard≥0.5 匹配)与 AI 区描述(仅精确键)贴到 payload。"""
    meta = _load_meta(config, lens)
    members_by_cluster: dict[str, list[str]] = {}
    for n in payload.get("nodes") or []:
        members_by_cluster.setdefault(n["cluster"], []).append(n["id"])
    for c in payload.get("clusters") or []:
        members = members_by_cluster.get(c["id"], [])
        key = _members_key(members)
        c["members_key"] = key
        entry = meta.get(key)
        if entry is None and not c.get("misc"):
            mset = set(members)
            best, best_j = None, 0.5
            for k, e in meta.items():
                j = _jaccard(mset, set(e.get("members") or []))
                if j >= best_j and e.get("label"):
                    best, best_j = e, j
            if best is not None:
                c["label"] = best["label"]
                c["label_overridden"] = True
            continue
        if entry:
            if entry.get("label"):
                c["label"] = entry["label"]
                c["label_overridden"] = True
            if entry.get("description"):
                c["description"] = entry["description"]
    return payload


def set_cluster_label(config: AppConfig, lens: str, cluster_id: str, label: str) -> dict:
    """人工区名:按当前成员快照存,后续重算的区经 Jaccard 匹配继续生效(人工优先)。"""
    payload = lens_payload(config, lens)
    members = [n["id"] for n in payload.get("nodes") or [] if n["cluster"] == cluster_id]
    if not members:
        raise ValueError(f"unknown cluster: {cluster_id}")
    key = _members_key(members)
    meta = _load_meta(config, lens)
    entry = meta.get(key) or {"members": sorted(members)}
    entry["label"] = label.strip()
    entry["members"] = sorted(members)
    meta[key] = entry
    _save_meta(config, lens, meta)
    return {"lens": lens, "cluster_id": cluster_id, "label": entry["label"], "members_key": key}


_DESCRIBE_SYSTEM = (
    "你为一张文献知识地图的各个分区写描述。给定每个分区的自动名、高频研究要素和论文标题样本,"
    "为每区写一句中文描述(≤60字,说清这批文献共同研究什么,不要套话、不要逐篇罗列)。"
)
_DESCRIBE_HINT = (
    'Return only one JSON object: {"descriptions": [{"cluster_id": str, "sentence": str}]}. '
    "Do not wrap the JSON in Markdown."
)


def describe_clusters(config: AppConfig, lens: str, client) -> dict:
    """给缺描述的区批量生成一句话(1 次 AI 调用/镜头);按成员哈希缓存,成员变才重生成。"""
    payload = lens_payload(config, lens)
    meta = _load_meta(config, lens)
    titles: dict[str, str] = {}
    for paper_dir in _all_paper_dirs(config):
        t = (_load_card(paper_dir).get("paper") or {}).get("title") or ""
        titles[paper_dir.name] = str(t)
    members_by_cluster: dict[str, list[str]] = {}
    for n in payload.get("nodes") or []:
        members_by_cluster.setdefault(n["cluster"], []).append(n["id"])

    todo = []
    for c in payload.get("clusters") or []:
        if c.get("misc") or c.get("description"):
            continue
        members = members_by_cluster.get(c["id"], [])
        todo.append({
            "cluster_id": c["id"],
            "auto_label": c["label"],
            "n_papers": len(members),
            "title_samples": [titles[m] for m in members[:12] if titles.get(m)],
        })
    stats = {"generated": 0, "ai_calls": 0, "already": len(payload.get("clusters") or []) - len(todo)}
    if not todo or client is None:
        return {**stats, "clusters": payload.get("clusters") or []}

    raw = client.chat_json(
        [{"role": "system", "content": _DESCRIBE_SYSTEM},
         {"role": "user", "content": json.dumps({"lens": lens, "clusters": todo}, ensure_ascii=False)}],
        _DESCRIBE_HINT,
    )
    stats["ai_calls"] = 1
    sentences = {}
    for d in (raw.get("descriptions") or []):
        if isinstance(d, dict) and d.get("cluster_id") and d.get("sentence"):
            sentences[str(d["cluster_id"])] = str(d["sentence"])[:120]
    for c in payload.get("clusters") or []:
        s = sentences.get(c["id"])
        if not s:
            continue
        members = members_by_cluster.get(c["id"], [])
        key = _members_key(members)
        entry = meta.get(key) or {"members": sorted(members)}
        entry["description"] = s
        entry["members"] = sorted(members)
        meta[key] = entry
        c["description"] = s
        stats["generated"] += 1
    _save_meta(config, lens, meta)
    return {**stats, "clusters": payload.get("clusters") or []}


def neighbors(config: AppConfig, lens: str, paper_id: str, k: int = 8) -> dict:
    """焦点论文在该镜头下共享要素最强的 top-k 邻居(spec §4 特写外环的真口径)。"""
    if lens not in LENS_FACETS:
        lens = "topic"
    feats = paper_features(config.elements_db, config.library_dir, lens)
    mine = feats.get(paper_id, set())
    weights = idf(feats)
    names = element_names(config.elements_db) if config.elements_db.exists() else {}
    scored = []
    for other, elems in feats.items():
        if other == paper_id:
            continue
        shared = mine & elems
        s = sum(weights.get(e, 0.0) for e in shared)
        if s > 0:
            top_shared = sorted(shared, key=lambda e: (-weights.get(e, 0.0), e))[:3]
            scored.append({
                "paper_id": other,
                "score": round(s, 3),
                "shared": [names.get(e, e.rsplit("/", 1)[-1]) for e in top_shared],
            })
    scored.sort(key=lambda d: (-d["score"], d["paper_id"]))
    return {"paper_id": paper_id, "lens": lens, "neighbors": scored[:k]}


def _paper_years(config: AppConfig) -> dict[str, int]:
    out: dict[str, int] = {}
    for paper_dir in _all_paper_dirs(config):
        year = (_load_card(paper_dir).get("paper") or {}).get("year")
        try:
            if year is not None:
                out[paper_dir.name] = int(year)
        except (TypeError, ValueError):
            continue
    return out


def element_first_seen(config: AppConfig, element_id: str) -> dict:
    """某要素在本库最早出现的年份与论文(年份未知的论文不参与)。"""
    years = _paper_years(config)
    conn = sqlite3.connect(config.elements_db)
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        papers = [r[0] for r in conn.execute(
            "SELECT DISTINCT paper_id FROM occurrences WHERE element_id=?", (element_id,))]
    finally:
        conn.close()
    dated = sorted(((years[p], p) for p in papers if p in years))
    if not dated:
        return {"element_id": element_id, "first_year": None, "first_paper": None,
                "papers_total": len(papers)}
    return {"element_id": element_id, "first_year": dated[0][0], "first_paper": dated[0][1],
            "papers_total": len(papers)}


def first_seen_in_range(config: AppConfig, year_from: int, year_to: int, top_n: int = 12) -> dict:
    """该年代区间内"首次出现"的要素,按总使用论文数排序(时间镜头年代带面板)。"""
    years = _paper_years(config)
    conn = sqlite3.connect(config.elements_db)
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        rows = list(conn.execute(
            "SELECT element_id, paper_id FROM occurrences WHERE role='used' GROUP BY element_id, paper_id"))
        names = {eid: nm for eid, nm in conn.execute("SELECT element_id, display_name FROM elements")}
    finally:
        conn.close()
    papers_of: dict[str, list[str]] = {}
    for eid, pid in rows:
        papers_of.setdefault(eid, []).append(pid)
    out = []
    for eid, papers in papers_of.items():
        dated = sorted((years[p], p) for p in papers if p in years)
        if not dated:
            continue
        fy, fp = dated[0]
        if year_from <= fy <= year_to:
            out.append({"element_id": eid, "name": names.get(eid, eid),
                        "first_year": fy, "first_paper": fp, "papers_total": len(papers)})
    out.sort(key=lambda d: (-d["papers_total"], d["element_id"]))
    return {"year_from": year_from, "year_to": year_to, "elements": out[:top_n]}


def institution_elements(config: AppConfig, inst_id: str, top_per_facet: int = 5) -> dict:
    """机构×要素交叉:该机构论文的要素分布("这个所偏 GCMC/那个组全是实验")。零 AI。"""
    papers = sorted(
        p.name for p in _all_paper_dirs(config)
        if inst_id in _paper_institutions(p)
    )
    if not papers or not config.elements_db.exists():
        return {"institution_id": inst_id, "papers": papers, "facets": {}}
    conn = sqlite3.connect(config.elements_db)
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        ph = ",".join("?" * len(papers))
        rows = list(conn.execute(
            f"SELECT o.facet, e.display_name, COUNT(DISTINCT o.paper_id) AS n "
            f"FROM occurrences o JOIN elements e ON e.element_id = o.element_id "
            f"WHERE o.role='used' AND o.paper_id IN ({ph}) "
            f"GROUP BY o.facet, o.element_id ORDER BY o.facet, n DESC, e.display_name",
            papers))
    finally:
        conn.close()
    facets: dict[str, list[dict]] = {}
    for facet, name, n in rows:
        bucket = facets.setdefault(facet, [])
        if len(bucket) < top_per_facet:
            bucket.append({"name": name, "papers": n})
    return {"institution_id": inst_id, "papers": papers, "facets": facets}


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
