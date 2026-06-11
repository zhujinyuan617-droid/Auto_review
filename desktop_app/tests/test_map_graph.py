import json
import math
from pathlib import Path

from autoreview_app.map.graph import (
    idf,
    label_propagation,
    name_clusters,
    paper_features,
    similarity_edges,
)


def test_idf_formula():
    feats = {"A": {"x", "y"}, "B": {"x"}, "C": {"x", "z"}}
    w = idf(feats)
    assert math.isclose(w["x"], math.log(3 / 3))  # 烂大街 → 0
    assert math.isclose(w["y"], math.log(3 / 1))
    assert math.isclose(w["z"], math.log(3 / 1))
    assert idf({}) == {}


def test_similarity_edges_idf_weighted_and_topk():
    feats = {
        "A": {"rare1", "common"},
        "B": {"rare1", "common"},
        "C": {"common"},
        "D": {"rare2"},
    }
    w = idf(feats)
    edges = similarity_edges(feats, w, top_k=10)
    pairs = {(a, b): s for a, b, s in edges}
    assert ("A", "B") in pairs                     # 共享 rare1(+common)
    assert pairs[("A", "B")] > pairs.get(("A", "C"), 0.0)  # 罕见要素压过烂大街
    assert all("D" not in (a, b) for a, b, _ in edges)     # 无共享 → 无边

    # top_k=1:每篇只留最强邻
    edges1 = similarity_edges(feats, w, top_k=1)
    assert ("A", "B") in {(a, b) for a, b, _ in edges1}


def test_label_propagation_two_blobs_deterministic():
    # 两团:A1-A2-A3 全连,B1-B2-B3 全连,团间无边
    nodes = ["A1", "A2", "A3", "B1", "B2", "B3"]
    edges = [("A1", "A2", 1.0), ("A2", "A3", 1.0), ("A1", "A3", 1.0),
             ("B1", "B2", 1.0), ("B2", "B3", 1.0), ("B1", "B3", 1.0)]
    l1 = label_propagation(nodes, edges)
    l2 = label_propagation(nodes, edges)
    assert l1 == l2                                  # 确定性
    assert l1["A1"] == l1["A2"] == l1["A3"]
    assert l1["B1"] == l1["B2"] == l1["B3"]
    assert l1["A1"] != l1["B1"]                      # 两区
    # 孤立点保持自标签
    l3 = label_propagation(["X", *nodes], edges)
    assert l3["X"] == "X"


def test_name_clusters_prefers_representative_over_universal():
    # 双区:e_univ 全员都有(零区分度);e_a 是 A 区专属、e_b 是 B 区专属。
    feats = {"A1": {"e_univ", "e_a"}, "A2": {"e_univ", "e_a"},
             "B1": {"e_univ", "e_b"}, "B2": {"e_univ", "e_b"}}
    w = idf(feats)
    labels = {"A1": "a", "A2": "a", "B1": "b", "B2": "b"}
    names = {"e_univ": "Universal", "e_a": "Alpha Thing", "e_b": "Beta Thing"}
    out = name_clusters(labels, feats, w, names, top_n=1)
    assert out["a"] == "Alpha Thing"                 # lift 胜过全员高频词
    assert out["b"] == "Beta Thing"


def test_similarity_edges_df_cap_drops_universal_glue():
    # 12 篇库:e_univ 出现 11/12(准烂大街,IDF>0 会黏合两团);cap=0.5 → 上限 6 → 剔除
    feats = {f"A{i}": {"e_univ", "e_a"} for i in range(6)}
    feats.update({f"B{i}": {"e_univ", "e_b"} for i in range(6)})
    feats["B5"] = {"e_b"}  # e_univ df=11
    w = idf(feats)
    glued = similarity_edges(feats, w, df_cap_ratio=1.0)
    assert any(a.startswith("A") and b.startswith("B") for a, b, _ in glued)
    cut = similarity_edges(feats, w, df_cap_ratio=0.5)
    assert all(not (a.startswith("A") and b.startswith("B")) for a, b, _ in cut)
    # 团内的真实边仍在
    assert any(a.startswith("A") and b.startswith("A") for a, b, _ in cut)


def test_split_oversized_breaks_mega_cluster():
    from autoreview_app.map.graph import split_oversized
    # 一个 8 节点"巨型区":两团各自强连(w=3),团间一条弱边(w=0.5)粘着
    nodes = [f"A{i}" for i in range(4)] + [f"B{i}" for i in range(4)]
    edges = []
    for grp in ("A", "B"):
        ids = [n for n in nodes if n.startswith(grp)]
        edges += [(ids[i], ids[j], 3.0) for i in range(4) for j in range(i + 1, 4)]
    edges.append(("A0", "B0", 0.5))
    labels = {n: "mega" for n in nodes}
    out = split_oversized(labels, edges, max_size=5)
    assert len({v for v in out.values()}) == 2       # 拆成两个子区
    assert out["A0"] == out["A3"] and out["B0"] == out["B3"]
    assert out["A0"] != out["B0"]
    assert all(v.startswith("mega>") for v in out.values())  # 子区带父前缀
    # 不超限的区原样不动
    small = {n: "s" for n in nodes[:3]}
    assert split_oversized(small, edges, max_size=5) == small


def _write_card(lib: Path, pid: str, topic_ids):
    d = lib / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "literature_card.json").write_text(
        json.dumps({"paper_id": pid, "classification": {"topic_ids": topic_ids}}),
        encoding="utf-8")


def test_split_oversized_anchor_fallback_breaks_dense_core():
    """T2(opus 评审):完全图等权密核——标签传播必然单标签,锚分组兜底必须把它分开。"""
    from autoreview_app.map.graph import split_oversized
    nodes = [f"A{i}" for i in range(4)] + [f"B{i}" for i in range(4)] + [f"C{i}" for i in range(4)]
    edges = [(a, b, 1.0) for i, a in enumerate(nodes) for b in nodes[i + 1:]]  # 完全图等权
    feats = {n: ({"fa"} if n.startswith("A") else {"fb"} if n.startswith("B") else set())
             for n in nodes}
    w = {"fa": 1.0, "fb": 1.0}
    labels = {n: "core" for n in nodes}
    out = split_oversized(labels, edges, max_size=6, features=feats, weights=w)
    assert out["A0"] == out["A3"] and out["B0"] == out["B3"]
    assert out["A0"] != out["B0"]                    # 按锚分了家
    assert out["C0"] != out["A0"]                    # 无锚者自成 __none__ 组
    assert all(v.startswith("core>") for v in out.values())


def test_merge_tiny_respects_max_size_gate(tmp_path: Path):
    """T4(opus 评审 + v4.3 余量):多篇小桶严守容量(拆分不被合并复原);
    单篇允许 cap 的 5%(≥1)超容余量——防"最像的区正好满员→被迫零散"(S72/S91)。"""
    from autoreview_app.map.service import _merge_tiny_clusters
    labels = {"B1": "BIG", "B2": "BIG", "B3": "BIG", "B4": "BIG", "T1": "T"}
    edges = [("T1", "B1", 9.9)]
    # 无上限:并入 BIG
    out1 = _merge_tiny_clusters(labels, edges, min_size=2)
    assert out1["T1"] == "BIG"
    # 上限 4:BIG 已满,但 T1 是单篇 → 余量放行(4+1)
    out2 = _merge_tiny_clusters(labels, edges, min_size=2, max_size=4)
    assert out2["T1"] == "BIG"
    # 第二个单篇再来:余量已用尽 → 拒收落零散
    labels3 = {**labels, "T2": "T2x"}
    edges3 = [("T1", "B1", 9.9), ("T2", "B2", 8.8)]
    out3 = _merge_tiny_clusters(labels3, edges3, min_size=2, max_size=4)
    assert sorted([out3["T1"], out3["T2"]]) == ["BIG", "__misc__"]
    # 两篇小桶面对满员 BIG:严格守容,整桶落零散(拆分不复原)
    labels4 = {"B1": "BIG", "B2": "BIG", "B3": "BIG", "B4": "BIG", "P1": "P", "P2": "P"}
    edges4 = [("P1", "B1", 9.9), ("P2", "B1", 9.9)]
    out4 = _merge_tiny_clusters(labels4, edges4, min_size=3, max_size=4)
    assert out4["P1"] == "__misc__" and out4["P2"] == "__misc__"


def test_paper_features_topic_lens_reads_cards(tmp_path: Path):
    lib = tmp_path / "library"
    _write_card(lib, "S01", ["elem:topic/shale-gas"])
    _write_card(lib, "S02", [])
    feats = paper_features(tmp_path / "nodb.sqlite", lib, "topic")
    assert feats["S01"] == {"elem:topic/shale-gas"}
    assert feats["S02"] == set()


def test_paper_features_method_lens_reads_index(tmp_path: Path):
    import sqlite3
    db = tmp_path / "elements_index.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        "CREATE TABLE elements (element_id TEXT PRIMARY KEY, facet TEXT, slug TEXT,"
        " display_name TEXT, aliases_json TEXT, human_locked INTEGER);"
        "CREATE TABLE occurrences (paper_id TEXT, element_id TEXT, facet TEXT, surface TEXT,"
        " quote TEXT, reading_block_id TEXT, role TEXT, digits_verified INTEGER, values_json TEXT);")
    rows = [
        ("S01", "elem:simulation/gcmc", "simulation", "GCMC", "q", "S01-RB-0001", "used", 0, "[]"),
        ("S01", "elem:material/quartz", "material", "quartz", "q", "S01-RB-0002", "used", 0, "[]"),
        ("S02", "elem:simulation/gcmc", "simulation", "GCMC", "q", "S02-RB-0001", "mentioned", 0, "[]"),
    ]
    conn.executemany("INSERT INTO occurrences VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()
    feats = paper_features(db, tmp_path / "library", "method")
    assert feats["S01"] == {"elem:simulation/gcmc"}   # material 不入 method 镜头
    assert "S02" not in feats                          # mentioned 不算 used
