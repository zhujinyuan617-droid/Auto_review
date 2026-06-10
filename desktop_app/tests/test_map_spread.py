import math

from autoreview_app.map.layout import fr_layout, spread_clusters


def _dist(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def _centroid(pos, ids):
    return (sum(pos[i][0] for i in ids) / len(ids), sum(pos[i][1] for i in ids) / len(ids))


NODES = [f"A{i}" for i in range(6)] + [f"B{i}" for i in range(6)]
EDGES = [(f"A{i}", f"A{j}", 1.0) for i in range(6) for j in range(i + 1, 6)] + \
        [(f"B{i}", f"B{j}", 1.0) for i in range(6) for j in range(i + 1, 6)]
CLUSTERS = {n: n[0] for n in NODES}


def test_spread_separates_centroids_and_keeps_membership():
    pos = fr_layout(NODES, EDGES, CLUSTERS)
    out = spread_clusters(pos, CLUSTERS)
    ca = _centroid(out, [n for n in NODES if n[0] == "A"])
    cb = _centroid(out, [n for n in NODES if n[0] == "B"])
    assert _dist(ca, cb) > 0.25                     # 区间留出空隙
    for n in NODES:                                  # 成员仍贴自己的区
        own, other = (ca, cb) if n[0] == "A" else (cb, ca)
        assert _dist(out[n], own) < _dist(out[n], other)


def test_spread_enforces_min_node_distance():
    pos = {n: (0.5, 0.5) for n in NODES}             # 全员重叠的极端输入
    out = spread_clusters(pos, CLUSTERS)
    ids = sorted(out)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            assert _dist(out[a], out[b]) >= 0.010    # 弛豫后不再叠点(留一点数值余量)


def test_spread_deterministic_and_bounded():
    pos = fr_layout(NODES, EDGES, CLUSTERS)
    o1 = spread_clusters(pos, CLUSTERS)
    o2 = spread_clusters(pos, CLUSTERS)
    assert o1 == o2
    for x, y in o1.values():
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def test_spread_many_singletons_stay_bounded():
    nodes = [f"S{i:02d}" for i in range(70)]
    pos = {n: (0.5 + (i % 7) * 0.001, 0.5 + (i // 7) * 0.001) for i, n in enumerate(nodes)}
    clusters = {n: n for n in nodes}                 # 70 个单点区(method 镜头形态)
    out = spread_clusters(pos, clusters)
    for x, y in out.values():
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def test_spread_single_cluster_noop_shape():
    pos = {"A": (0.2, 0.2), "B": (0.8, 0.8)}
    out = spread_clusters(pos, {"A": "x", "B": "x"})
    assert set(out) == {"A", "B"}
