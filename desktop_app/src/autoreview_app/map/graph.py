"""Map graph math: lens features, IDF similarity, clustering, region naming.

纯函数、零 AI、确定性(同输入恒同输出)。设计:specs/2026-06-09-map-home-design.md §3。
相似度 = 两篇共享要素的 IDF 加权和(罕见要素加分大,"都研究吸附"几乎不加分),
与 connect/build_candidate_edges.py 同配方,但算在镜头的 facet 子集上。
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

# 镜头 → 参与相似度的 facet 子集;time/institution 镜头不走要素相似度(见 service)。
LENS_FACETS: dict[str, tuple[str, ...]] = {
    "topic": ("topic",),
    "method": ("preparation", "measurement", "simulation"),
    "material": ("material",),
}


def paper_features(db_path: Path, library_dir: Path, lens: str) -> dict[str, set[str]]:
    """每篇论文在该镜头下的要素集合。topic 镜头读卡片 topic_ids(机械派生,索引里无)。"""
    if lens == "topic":
        feats: dict[str, set[str]] = {}
        for p in sorted(Path(library_dir).glob("*/literature_card.json")):
            card = json.loads(p.read_text(encoding="utf-8"))
            ids = (card.get("classification") or {}).get("topic_ids") or []
            feats[p.parent.name] = {str(i) for i in ids}
        return feats
    facets = LENS_FACETS[lens]
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        placeholders = ",".join("?" * len(facets))
        rows = conn.execute(
            f"SELECT DISTINCT paper_id, element_id FROM occurrences "
            f"WHERE role='used' AND facet IN ({placeholders})",
            facets,
        )
        feats = {}
        for paper_id, eid in rows:
            feats.setdefault(paper_id, set()).add(eid)
    finally:
        conn.close()
    return feats


def idf(features: dict[str, set[str]]) -> dict[str, float]:
    """log(N/df);df=含该要素的论文数。N=0 → 空表。"""
    n = len(features)
    if n == 0:
        return {}
    df: dict[str, int] = {}
    for elems in features.values():
        for e in elems:
            df[e] = df.get(e, 0) + 1
    return {e: math.log(n / d) for e, d in df.items()}


def similarity_edges(
    features: dict[str, set[str]], weights: dict[str, float],
    top_k: int = 10, min_score: float = 0.0,
) -> list[tuple[str, str, float]]:
    """共享要素 IDF 和;每篇保 top-k 邻居;返回去重无向边 (a<b, score)。"""
    papers = sorted(features)
    # 倒排:要素 → 含它的论文,避免 O(n^2) 全比对
    inverted: dict[str, list[str]] = {}
    for pid in papers:
        for e in features[pid]:
            inverted.setdefault(e, []).append(pid)
    scores: dict[tuple[str, str], float] = {}
    for e, members in inverted.items():
        w = weights.get(e, 0.0)
        if w <= 0 or len(members) < 2:
            continue
        for i, a in enumerate(members):
            for b in members[i + 1:]:
                key = (a, b) if a < b else (b, a)
                scores[key] = scores.get(key, 0.0) + w
    # 每篇 top-k 截断(任一端保留即保留该边——与候选边口径一致)
    per_paper: dict[str, list[tuple[float, tuple[str, str]]]] = {p: [] for p in papers}
    for key, s in scores.items():
        if s <= min_score:
            continue
        per_paper[key[0]].append((s, key))
        per_paper[key[1]].append((s, key))
    kept: set[tuple[str, str]] = set()
    for p, lst in per_paper.items():
        lst.sort(key=lambda t: (-t[0], t[1]))
        kept.update(key for _, key in lst[:top_k])
    return sorted(((a, b, scores[(a, b)]) for a, b in kept), key=lambda t: (t[0], t[1]))


def label_propagation(
    nodes: list[str], edges: list[tuple[str, str, float]], iters: int = 20,
) -> dict[str, str]:
    """确定性标签传播:初始自标签;按节点名顺序逐点更新为邻居加权多数票,平票取标签字典序小者。"""
    adj: dict[str, list[tuple[str, float]]] = {n: [] for n in nodes}
    for a, b, w in edges:
        if a in adj and b in adj:
            adj[a].append((b, w))
            adj[b].append((a, w))
    labels = {n: n for n in sorted(nodes)}
    for _ in range(iters):
        changed = False
        for n in sorted(nodes):
            if not adj[n]:
                continue
            votes: dict[str, float] = {}
            for nb, w in adj[n]:
                votes[labels[nb]] = votes.get(labels[nb], 0.0) + w
            best = sorted(votes.items(), key=lambda t: (-t[1], t[0]))[0][0]
            if best != labels[n]:
                labels[n] = best
                changed = True
        if not changed:
            break
    return labels


def name_clusters(
    labels: dict[str, str], features: dict[str, set[str]],
    weights: dict[str, float], names: dict[str, str], top_n: int = 2,
) -> dict[str, str]:
    """区名 = 区内最高频要素的 display_name(排除 idf 最低 30% 的"烂大街"项),取 1–2 个连「·」。"""
    if weights:
        sorted_w = sorted(weights.values())
        floor = sorted_w[int(len(sorted_w) * 0.3)]
    else:
        floor = 0.0
    filtered: dict[str, dict[str, int]] = {}
    unfiltered: dict[str, dict[str, int]] = {}
    for pid, label in labels.items():
        for e in features.get(pid, ()):
            unfiltered.setdefault(label, {}).setdefault(e, 0)
            unfiltered[label][e] += 1
            if weights.get(e, 0.0) <= floor:  # 底部 30%(含分位线上的"烂大街")排除
                continue
            filtered.setdefault(label, {}).setdefault(e, 0)
            filtered[label][e] += 1
    out: dict[str, str] = {}
    for label in {v for v in labels.values()}:
        counts = filtered.get(label) or unfiltered.get(label, {})  # 全被排掉 → 回退不过滤
        top = sorted(counts.items(), key=lambda t: (-t[1], -weights.get(t[0], 0.0), t[0]))[:top_n]
        out[label] = " · ".join(names.get(e, e.rsplit("/", 1)[-1]) for e, _ in top) or "未命名区"
    return out


def element_names(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        return {eid: name for eid, name in conn.execute("SELECT element_id, display_name FROM elements")}
    finally:
        conn.close()
