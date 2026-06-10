"""Deterministic force layout + incremental placement + cache fingerprint.

设计 §3:位置要稳定——全量布局只在缓存失效或显式重排时;新论文以最近邻为锚增量落位,
老点坐标一律不动。全部确定性(固定 seed / 按 id 排序 / 哈希微偏),禁时钟与全局随机。
"""
from __future__ import annotations

import hashlib
import json
import math
import random

SCHEMA_VERSION = "0.1.0"


def fingerprint(lens: str, features: dict[str, set[str]], params: dict) -> str:
    """参数或任一篇的要素集变化 → 指纹变化 → 全量重算。"""
    payload = {
        "lens": lens,
        "params": {k: params[k] for k in sorted(params)},
        "papers": {pid: sorted(features[pid]) for pid in sorted(features)},
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()


def _normalize(pos: dict[str, tuple[float, float]], pad: float = 0.05) -> dict[str, tuple[float, float]]:
    if not pos:
        return {}
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    dx = (max(xs) - min(xs)) or 1.0
    dy = (max(ys) - min(ys)) or 1.0
    span = 1.0 - 2 * pad
    return {
        n: (pad + span * (x - min(xs)) / dx, pad + span * (y - min(ys)) / dy)
        for n, (x, y) in pos.items()
    }


def fr_layout(
    nodes: list[str], edges: list[tuple[str, str, float]], clusters: dict[str, str],
    iters: int = 150, seed: int = 42, gravity: float = 0.05,
) -> dict[str, tuple[float, float]]:
    """Fruchterman–Reingold + 同区向质心的引力;261 点量级秒级,产物进缓存。"""
    snodes = sorted(nodes)
    if not snodes:
        return {}
    rng = random.Random(seed)
    pos = {n: [rng.random(), rng.random()] for n in snodes}
    if len(snodes) == 1:
        return {snodes[0]: (0.5, 0.5)}
    k = math.sqrt(1.0 / len(snodes))
    max_w = max((w for _, _, w in edges), default=1.0) or 1.0
    temp = 0.1
    cool = temp / (iters + 1)
    for _ in range(iters):
        disp = {n: [0.0, 0.0] for n in snodes}
        # 斥力(全对)
        for i, a in enumerate(snodes):
            ax, ay = pos[a]
            for b in snodes[i + 1:]:
                dx = ax - pos[b][0]
                dy = ay - pos[b][1]
                d2 = dx * dx + dy * dy + 1e-9
                f = k * k / d2
                disp[a][0] += dx * f
                disp[a][1] += dy * f
                disp[b][0] -= dx * f
                disp[b][1] -= dy * f
        # 引力(沿边,按权重缩放)
        for a, b, w in edges:
            if a not in pos or b not in pos:
                continue
            dx = pos[a][0] - pos[b][0]
            dy = pos[a][1] - pos[b][1]
            d = math.sqrt(dx * dx + dy * dy) + 1e-9
            f = d * d / k * (0.2 + 0.8 * w / max_w)
            disp[a][0] -= dx / d * f * d
            disp[a][1] -= dy / d * f * d
            disp[b][0] += dx / d * f * d
            disp[b][1] += dy / d * f * d
        # 同区质心引力
        centroids: dict[str, list[float]] = {}
        counts: dict[str, int] = {}
        for n in snodes:
            c = clusters.get(n, n)
            cx = centroids.setdefault(c, [0.0, 0.0])
            cx[0] += pos[n][0]
            cx[1] += pos[n][1]
            counts[c] = counts.get(c, 0) + 1
        for c in centroids:
            centroids[c][0] /= counts[c]
            centroids[c][1] /= counts[c]
        for n in snodes:
            c = clusters.get(n, n)
            disp[n][0] += (centroids[c][0] - pos[n][0]) * gravity
            disp[n][1] += (centroids[c][1] - pos[n][1]) * gravity
        # 位移截断 + 降温
        for n in snodes:
            dx, dy = disp[n]
            d = math.sqrt(dx * dx + dy * dy) + 1e-9
            step = min(d, temp)
            pos[n][0] += dx / d * step
            pos[n][1] += dy / d * step
        temp = max(temp - cool, 1e-4)
    return _normalize({n: (p[0], p[1]) for n, p in pos.items()})


def spread_clusters(
    pos: dict[str, tuple[float, float]], clusters: dict[str, str], iters: int = 60,
) -> dict[str, tuple[float, float]]:
    """区级分离后处理:每区按规模分配半径,质心互斥到不重叠,成员缩放进own半径,
    最后全局点间最小距弛豫——治"全图挤成一团、区界不清"。确定性。"""
    members: dict[str, list[str]] = {}
    for n, c in clusters.items():
        if n in pos:
            members.setdefault(c, []).append(n)
    if len(members) <= 1:
        return dict(pos)
    total = sum(len(v) for v in members.values())
    cents: dict[str, list[float]] = {}
    radii: dict[str, float] = {}
    for c in sorted(members):
        ms = members[c]
        cents[c] = [sum(pos[m][0] for m in ms) / len(ms), sum(pos[m][1] for m in ms) / len(ms)]
        radii[c] = 0.04 + 0.30 * math.sqrt(len(ms) / total)
    cids = sorted(cents)
    for _ in range(iters):
        moved = False
        for i, a in enumerate(cids):
            for b in cids[i + 1:]:
                dx = cents[a][0] - cents[b][0]
                dy = cents[a][1] - cents[b][1]
                d = math.hypot(dx, dy) or 1e-6
                want = radii[a] + radii[b] + 0.015
                if d < want:
                    push = (want - d) / 2
                    cents[a][0] += dx / d * push
                    cents[a][1] += dy / d * push
                    cents[b][0] -= dx / d * push
                    cents[b][1] -= dy / d * push
                    moved = True
        if not moved:
            break
    out: dict[str, list[float]] = {}
    for c in cids:
        ms = members[c]
        ocx = sum(pos[m][0] for m in ms) / len(ms)
        ocy = sum(pos[m][1] for m in ms) / len(ms)
        maxoff = max((math.hypot(pos[m][0] - ocx, pos[m][1] - ocy) for m in ms), default=0.0)
        scale = min((radii[c] * 0.8) / max(maxoff, 1e-6), 3.0)
        for m in ms:
            out[m] = [cents[c][0] + (pos[m][0] - ocx) * scale,
                      cents[c][1] + (pos[m][1] - ocy) * scale]
    ids = sorted(out)
    min_d = 0.014
    for _ in range(25):
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                dx = out[a][0] - out[b][0]
                dy = out[a][1] - out[b][1]
                d = math.hypot(dx, dy)
                if d < min_d:
                    if d < 1e-9:
                        # 完全重合:零向量推不开 → 按点对 id 哈希取确定性方向
                        h = hashlib.sha256(f"{a}|{b}".encode("utf-8")).digest()
                        ang = h[0] / 255 * 2 * math.pi
                        ux, uy = math.cos(ang), math.sin(ang)
                    else:
                        ux = dx / d
                        uy = dy / d
                    push = (min_d - d) / 2 + 1e-4
                    out[a][0] += ux * push
                    out[a][1] += uy * push
                    out[b][0] -= ux * push
                    out[b][1] -= uy * push
    return _normalize({n: (p[0], p[1]) for n, p in out.items()})


GOLDEN_ANGLE = math.pi * (3.0 - math.sqrt(5.0))


def _normalize_uniform(pos: dict[str, tuple[float, float]], pad: float = 0.05) -> dict[str, tuple[float, float]]:
    """等比缩放到画布(径向布局用:x/y 独立拉伸会把年轮压成椭圆)。"""
    if not pos:
        return {}
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    cx = (max(xs) + min(xs)) / 2
    cy = (max(ys) + min(ys)) / 2
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 1.0
    scale = (1.0 - 2 * pad) / span
    return {n: (0.5 + (x - cx) * scale, 0.5 + (y - cy) * scale) for n, (x, y) in pos.items()}


def radial_layout(
    members: dict[str, list[str]],
    order_key: dict[str, tuple],
    pinned: tuple[str, ...] = ("__misc__", "__unbuilt__"),
) -> dict[str, tuple[float, float]]:
    """权重向心 + 区内年轮(Wave-3 ①,替换 fr_layout+spread_clusters 的元素镜头布点)。

    - 区级:最大区放画布中心,其余按规模降序沿同心环排;pinned 区(零散/待构建)
      强制断环压最外圈。
    - 区内:成员按 order_key 升序(年份,平票按 id)沿黄金角螺旋铺开——
      半径随序号单调增,即"老文献靠区心、新文献靠区缘"的年轮。
    - 全确定性:无随机、无时钟;同输入同输出。
    """
    sizes = {c: len(ms) for c, ms in members.items() if ms}
    if not sizes:
        return {}
    total = sum(sizes.values())
    radii = {c: 0.05 + 0.22 * math.sqrt(sizes[c] / total) for c in sizes}
    pinned_set = set(pinned)
    normal = sorted((c for c in sizes if c not in pinned_set), key=lambda c: (-sizes[c], c))
    tail = sorted((c for c in sizes if c in pinned_set), key=lambda c: (-sizes[c], c))
    order = (normal + tail) or []

    GAP = 0.015
    cents: dict[str, tuple[float, float]] = {order[0]: (0.0, 0.0)}
    reach = radii[order[0]]  # 已占用的最大半径
    i = 1
    ring_no = 0
    while i < len(order):
        ring_no += 1
        d = reach + GAP + radii[order[i]]
        theta0 = ring_no * 0.7  # 环间起始角错位,防径向走廊
        theta = theta0
        ring_max = 0.0
        ring_has_normal = False
        while i < len(order):
            c = order[i]
            rc = radii[c]
            if c in pinned_set and ring_has_normal:
                break  # pinned 不与普通区同环:断环,保证它压最外圈
            ratio = (rc + GAP / 2) / d
            if ratio >= 0.9:
                if ring_max > 0.0:
                    break  # 区比当前环还大:自己另开一环
                half = math.pi  # 独占整环
            else:
                half = math.asin(ratio)
            if theta + 2 * half > theta0 + 2 * math.pi + 1e-9:
                break  # 本环角度排满
            cents[c] = (d * math.cos(theta + half), d * math.sin(theta + half))
            theta += 2 * half
            ring_max = max(ring_max, rc)
            ring_has_normal = ring_has_normal or c not in pinned_set
            i += 1
        reach = d + ring_max

    pos: dict[str, tuple[float, float]] = {}
    for c in order:
        ms = members[c]
        cx, cy = cents[c]
        rc = radii[c]
        ordered = sorted(ms, key=lambda p: order_key.get(p, ((1 << 31), p)))
        n = len(ordered)
        if n == 1:
            pos[ordered[0]] = (cx, cy)
            continue
        # 区相位按区 id 哈希,免得所有区的螺旋零点指向同一方向
        phase = int(hashlib.sha256(c.encode("utf-8")).hexdigest()[:8], 16) % 6283 / 1000.0
        for k, pid in enumerate(ordered):
            rr = rc * 0.85 * math.sqrt((k + 0.5) / n)
            th = phase + k * GOLDEN_ANGLE
            pos[pid] = (cx + rr * math.cos(th), cy + rr * math.sin(th))
    return _normalize_uniform(pos)


def _hash_jitter(pid: str, scale: float = 0.02) -> tuple[float, float]:
    h = hashlib.sha256(pid.encode("utf-8")).digest()
    return ((h[0] / 255 - 0.5) * 2 * scale, (h[1] / 255 - 0.5) * 2 * scale)


def incremental_place(
    old_pos: dict[str, tuple[float, float]],
    new_neighbors: dict[str, list[tuple[str, float]]],
    relax_iters: int = 30,
) -> dict[str, tuple[float, float]]:
    """新点 = top-3 老邻居的相似度加权质心 + 确定性微偏;无邻居 → 按 id 哈希角落在外环。
    只弛豫新点(老点冻结)。返回仅新点坐标。"""
    placed: dict[str, list[float]] = {}
    for pid in sorted(new_neighbors):
        nbs = [(n, w) for n, w in new_neighbors[pid] if n in old_pos][:3]
        jx, jy = _hash_jitter(pid)
        if nbs:
            total = sum(w for _, w in nbs) or 1.0
            x = sum(old_pos[n][0] * w for n, w in nbs) / total + jx
            y = sum(old_pos[n][1] * w for n, w in nbs) / total + jy
        else:
            angle = (hashlib.sha256(pid.encode("utf-8")).digest()[2] / 255) * 2 * math.pi
            x = 0.5 + 0.45 * math.cos(angle) + jx
            y = 0.5 + 0.45 * math.sin(angle) + jy
        placed[pid] = [min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)]
    # 新点间互斥弛豫(避免同锚重叠;老点不动)
    new_ids = sorted(placed)
    for _ in range(relax_iters):
        for i, a in enumerate(new_ids):
            for b in new_ids[i + 1:]:
                dx = placed[a][0] - placed[b][0]
                dy = placed[a][1] - placed[b][1]
                d = math.sqrt(dx * dx + dy * dy)
                if d < 0.02:
                    push = (0.02 - d) / 2 + 1e-3
                    nx = dx / (d + 1e-9)
                    ny = dy / (d + 1e-9)
                    placed[a][0] = min(max(placed[a][0] + nx * push, 0.0), 1.0)
                    placed[a][1] = min(max(placed[a][1] + ny * push, 0.0), 1.0)
                    placed[b][0] = min(max(placed[b][0] - nx * push, 0.0), 1.0)
                    placed[b][1] = min(max(placed[b][1] - ny * push, 0.0), 1.0)
    return {pid: (p[0], p[1]) for pid, p in placed.items()}
