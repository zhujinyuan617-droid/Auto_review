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


# ---------------------------------------------------------------------------
# Wave-3 ①:radial_layout(权重向心 + 区内年轮 + pinned 区压最外圈)
# ---------------------------------------------------------------------------

from autoreview_app.map.layout import radial_layout  # noqa: E402


def _members(spec):
    """spec: {cluster: n} → 生成成员表 + 年份序键(成员 i 年份 2000+i)。"""
    members = {c: [f"{c}{i:02d}" for i in range(n)] for c, n in spec.items()}
    order_key = {p: (2000 + i, p)
                 for c, ms in members.items() for i, p in enumerate(ms)}
    return members, order_key


def _centroid(pos, ms):
    xs = [pos[m][0] for m in ms]
    ys = [pos[m][1] for m in ms]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def test_radial_deterministic_and_bounded():
    members, key = _members({"big": 20, "m1": 8, "m2": 8, "s1": 3})
    p1 = radial_layout(members, key)
    p2 = radial_layout(members, key)
    assert p1 == p2
    assert set(p1) == {m for ms in members.values() for m in ms}
    for x, y in p1.values():
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


def test_radial_weight_centered_rings():
    # 6 个中区填满第一环,3 个小区被挤到更外环:小区质心离大区质心更远
    spec = {"big": 20}
    spec.update({f"m{i}": 8 for i in range(6)})
    spec.update({f"s{i}": 3 for i in range(3)})
    members, key = _members(spec)
    pos = radial_layout(members, key)
    c_big = _centroid(pos, members["big"])
    d_mid = max(_dist(c_big, _centroid(pos, members[f"m{i}"])) for i in range(6))
    d_small = min(_dist(c_big, _centroid(pos, members[f"s{i}"])) for i in range(3))
    assert d_small > d_mid  # 规模降序排环:小区在更外


def test_radial_year_rings_old_inside_new_outside():
    members, key = _members({"big": 20, "m1": 8})
    pos = radial_layout(members, key)
    ms = members["big"]  # 成员年份随序号递增(2000..2019)
    c = _centroid(pos, ms)
    d_old = _dist(c, pos[ms[0]])     # 最老
    d_mid = _dist(c, pos[ms[10]])    # 中段
    d_new = _dist(c, pos[ms[-1]])    # 最新
    assert d_old < d_mid < d_new     # 年轮:老内新外


def test_radial_pinned_clusters_outermost():
    # 待构建区比部分普通区还大,也必须压最外圈(断环规则)
    members, key = _members({"big": 15, "m1": 6, "m2": 5, "__unbuilt__": 10})
    pos = radial_layout(members, key)
    c_big = _centroid(pos, members["big"])
    d_unbuilt = _dist(c_big, _centroid(pos, members["__unbuilt__"]))
    for c in ("m1", "m2"):
        assert d_unbuilt > _dist(c_big, _centroid(pos, members[c])) - 1e-9


def test_radial_edge_cases():
    assert radial_layout({}, {}) == {}
    assert radial_layout({"only": ["X"]}, {"X": (2020, "X")}) == {"X": (0.5, 0.5)}
