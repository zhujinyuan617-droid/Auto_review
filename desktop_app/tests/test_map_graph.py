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


def test_name_clusters_excludes_low_idf():
    feats = {"A": {"e_rare", "e_common"}, "B": {"e_rare", "e_common"},
             "C": {"e_common"}, "D": {"e_common"}, "E": {"e_common"}}
    w = idf(feats)
    labels = {p: "A" for p in feats}
    names = {"e_rare": "Rare Thing", "e_common": "Common Thing"}
    out = name_clusters(labels, feats, w, names, top_n=1)
    assert out["A"] == "Rare Thing"                  # 烂大街被排除


def _write_card(lib: Path, pid: str, topic_ids):
    d = lib / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "literature_card.json").write_text(
        json.dumps({"paper_id": pid, "classification": {"topic_ids": topic_ids}}),
        encoding="utf-8")


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
