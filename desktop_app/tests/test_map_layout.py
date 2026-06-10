from autoreview_app.map.layout import fingerprint, fr_layout, incremental_place


NODES = ["A1", "A2", "A3", "B1", "B2", "B3"]
EDGES = [("A1", "A2", 2.0), ("A2", "A3", 2.0), ("A1", "A3", 2.0),
         ("B1", "B2", 2.0), ("B2", "B3", 2.0), ("B1", "B3", 2.0)]
CLUSTERS = {"A1": "a", "A2": "a", "A3": "a", "B1": "b", "B2": "b", "B3": "b"}


def _dist(p, q):
    return ((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2) ** 0.5


def test_fr_layout_deterministic_and_normalized():
    p1 = fr_layout(NODES, EDGES, CLUSTERS)
    p2 = fr_layout(NODES, EDGES, CLUSTERS)
    assert p1 == p2
    for x, y in p1.values():
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0
    # 同区点平均距离 < 异区点平均距离(聚拢生效)
    intra = (_dist(p1["A1"], p1["A2"]) + _dist(p1["B1"], p1["B2"])) / 2
    inter = _dist(p1["A1"], p1["B1"])
    assert intra < inter


def test_fr_layout_edge_cases():
    assert fr_layout([], [], {}) == {}
    assert fr_layout(["X"], [], {}) == {"X": (0.5, 0.5)}


def test_incremental_keeps_old_frozen_and_anchors_new():
    old = fr_layout(NODES, EDGES, CLUSTERS)
    new = incremental_place(old, {"N1": [("A1", 3.0), ("A2", 2.0), ("B1", 0.1)]})
    assert set(new) == {"N1"}
    # 落在 A 团附近而非 B 团
    assert _dist(new["N1"], old["A1"]) < _dist(new["N1"], old["B1"])
    # 老点坐标完全未动(incremental 不返回也不改 old)
    assert old == fr_layout(NODES, EDGES, CLUSTERS)


def test_incremental_isolated_goes_to_rim_deterministically():
    old = fr_layout(NODES, EDGES, CLUSTERS)
    n1 = incremental_place(old, {"LONELY": []})
    n2 = incremental_place(old, {"LONELY": []})
    assert n1 == n2
    x, y = n1["LONELY"]
    assert _dist((x, y), (0.5, 0.5)) > 0.3   # 外环,不混进中心


def test_incremental_two_new_same_anchor_do_not_overlap():
    old = fr_layout(NODES, EDGES, CLUSTERS)
    nbs = [("A1", 1.0)]
    new = incremental_place(old, {"N1": nbs, "N2": nbs})
    assert _dist(new["N1"], new["N2"]) >= 0.015


def test_fingerprint_sensitivity():
    feats = {"S01": {"e1"}, "S02": {"e1", "e2"}}
    params = {"top_k": 10, "iters": 150, "seed": 42}
    f1 = fingerprint("topic", feats, params)
    assert f1 == fingerprint("topic", {"S02": {"e2", "e1"}, "S01": {"e1"}}, dict(params))  # 顺序无关
    assert f1 != fingerprint("method", feats, params)                                      # 镜头敏感
    assert f1 != fingerprint("topic", {"S01": {"e1"}, "S02": {"e1"}}, params)              # 要素集敏感
    assert f1 != fingerprint("topic", feats, {**params, "top_k": 5})                       # 参数敏感
