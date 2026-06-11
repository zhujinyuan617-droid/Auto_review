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
    # 与论文卡/区画像的"方法"口径一致(五类);曾漏 analysis/characterization,
    # 4 篇用了分析/表征方法的论文被误标"无方法类要素"
    "method": ("preparation", "measurement", "simulation", "characterization", "analysis"),
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
    top_k: int = 10, min_score: float = 0.0, df_cap_ratio: float = 1.0,
) -> list[tuple[str, str, float]]:
    """共享要素 IDF 和;每篇保 top-k 邻居;返回去重无向边 (a<b, score)。

    df_cap_ratio<1 时,出现于超过该比例论文的"烂大街"要素不参与连边——
    内容审计(2026-06-10)证实:人人都用 MD/CH4 时 IDF 降权不够,巨型区由此而生。
    """
    papers = sorted(features)
    if df_cap_ratio < 1.0 and papers:
        # 保底 5:小库(含测试夹具)不触发——剔"烂大街"只在规模化语料上才有意义
        cap = max(5, int(len(papers) * df_cap_ratio))
        df: dict[str, int] = {}
        for elems in features.values():
            for e in elems:
                df[e] = df.get(e, 0) + 1
        banned = {e for e, d in df.items() if d > cap}
        if banned:
            features = {p: elems - banned for p, elems in features.items()}
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


def split_oversized(
    labels: dict[str, str], edges: list[tuple[str, str, float]],
    max_size: int = 30, depth: int = 0,
    features: dict[str, set[str]] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, str]:
    """巨型区递归再分:对超限区只用区内边重跑标签传播(剔掉区内的"烂大街"
    粘合边——保留强于区内边权中位数的边),分不动就保持原样。确定性。
    内容审计:topic 镜头 4 个巨型区(最大 61 篇)装走 58% 论文,必拆。"""
    if depth >= 4:
        return labels
    sizes: dict[str, list[str]] = {}
    for n, c in labels.items():
        sizes.setdefault(c, []).append(n)
    out = dict(labels)
    changed = False
    for cluster, members in sorted(sizes.items()):
        if len(members) <= max_size:
            continue
        mset = set(members)
        inner = [(a, b, w) for a, b, w in edges if a in mset and b in mset]
        if not inner:
            continue
        ws = sorted(w for _, _, w in inner)
        # 逐级抬高门槛(保留 ≥ 分位值的边)直到拆得动;全档拆不动则保持原样
        sub = None
        for q in (0.50, 0.75, 0.90, 0.97):
            floor = ws[min(int(len(ws) * q), len(ws) - 1)]
            strong = [(a, b, w) for a, b, w in inner if w >= floor]
            if not strong:
                continue
            cand = label_propagation(sorted(members), strong)
            if len({v for v in cand.values()}) > 1:
                sub = cand
                break
        if sub is None and features:
            # 密核:标签传播在稠密核上必然收敛单标签 → 退到语义分组——
            # 每篇取其"最具区分度的中频要素"(df∈[4, N/3])作锚,按锚归桶。
            n_total = len(features) or 1
            df: dict[str, int] = {}
            for elems in features.values():
                for e in elems:
                    df[e] = df.get(e, 0) + 1
            band_hi = max(5, n_total // 3)

            banned: set[str] = set()
            for _attempt in range(6):
                def _anchor(pid: str) -> str:
                    cands = [
                        ((weights or {}).get(e, 0.0), e)
                        for e in features.get(pid, ())
                        if 4 <= df.get(e, 0) <= band_hi and e not in banned
                    ]
                    # max 的平票语义:weight 相等时取 e 字典序**最大**者——确定即可,方向无关紧要
                    return max(cands)[1] if cands else "__none__"

                groups: dict[str, list[str]] = {}
                for n in sorted(members):
                    groups.setdefault(_anchor(n), []).append(n)
                if len(groups) > 1:
                    sub = {n: g for g, ms in groups.items() for n in ms}
                    break
                # 全员同锚(第二层密核):禁掉这个公共锚,用次选锚再分
                only = next(iter(groups))
                if only == "__none__":
                    break
                banned.add(only)
        if sub is None:
            continue
        # 子区编号带父前缀,保证全局唯一且确定
        for n in members:
            out[n] = f"{cluster}>{sub[n]}"
        changed = True
    if changed:
        return split_oversized(out, edges, max_size=max_size, depth=depth + 1,
                               features=features, weights=weights)
    return out


def name_clusters(
    labels: dict[str, str], features: dict[str, set[str]],
    weights: dict[str, float], names: dict[str, str], top_n: int = 2,
) -> dict[str, str]:
    """区名 = 区内"代表性"最高的要素:覆盖率(≥1/4 成员含它)× 区分度(对区外的提升倍数)。

    旧版按区内频次取词,巨型杂区里高频垃圾词会上位(审计实证:"biological·building
    materials" 命名了一个页岩运移区)。lift 评分让"区内常见、区外罕见"的词胜出;
    weights(IDF)仅作平票次序参考。
    """
    n_total = len(features) or 1
    df: dict[str, int] = {}
    for elems in features.values():
        for e in elems:
            df[e] = df.get(e, 0) + 1
    by_cluster: dict[str, dict[str, int]] = {}
    sizes: dict[str, int] = {}
    for pid, label in labels.items():
        sizes[label] = sizes.get(label, 0) + 1
        for e in features.get(pid, ()):
            by_cluster.setdefault(label, {}).setdefault(e, 0)
            by_cluster[label][e] += 1
    out: dict[str, str] = {}
    for label in {v for v in labels.values()}:
        counts = by_cluster.get(label, {})
        size = sizes.get(label, 1)
        scored: list[tuple[float, float, str]] = []
        for e, cin in counts.items():
            cov = cin / size
            out_rate = (df.get(e, cin) - cin + 0.5) / max(n_total - size, 1)
            lift = cov / max(out_rate, 1e-9)
            scored.append((cov * min(lift, 50.0), cov, e))
        good = [s for s in scored if s[1] >= 0.25]  # 1/4 成员都没有的词不配命名
        pick = sorted(good or scored, key=lambda t: (-t[0], -weights.get(t[2], 0.0), t[2]))[:top_n]
        out[label] = " · ".join(names.get(e, e.rsplit("/", 1)[-1]) for _, _, e in pick) or "未命名区"
    return out


def element_names(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        return {eid: name for eid, name in conn.execute("SELECT element_id, display_name FROM elements")}
    finally:
        conn.close()
