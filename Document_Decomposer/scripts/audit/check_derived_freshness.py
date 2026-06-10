"""Mechanical freshness gate for the derived chain (ISSUES I18 made executable).

链条:registry.json → vocabulary.json → candidate_edges.json → edges.json → concept_index.json
上游比下游新 = 下游过期(乱序重建会让候选边召回静默塌缩)。本脚本只读、只报告;
exit 0 = 全新鲜,exit 1 = 有过期(打印谁过期、该按什么顺序重跑)。
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# (名字, 路径, 依赖于哪些上游名字)
CHAIN = [
    ("registry", ROOT / "data" / "elements" / "registry.json", []),
    ("vocabulary", ROOT / "reports" / "connection" / "vocabulary.json", ["registry"]),
    ("candidate_edges", ROOT / "reports" / "connection" / "candidate_edges.json", ["vocabulary"]),
    ("edges", ROOT / "reports" / "connection" / "edges.json", ["candidate_edges"]),
    ("concept_index", ROOT / "reports" / "connection" / "concept_index.json", ["vocabulary"]),
]

REBUILD_HINT = {
    "vocabulary": "scripts/elements/derive_vocabulary.py",
    "candidate_edges": "scripts/connect/build_candidate_edges.py",
    "edges": "scripts/connect/ai_build_edges.py --config <ai.local.json> --workers 48",
    "concept_index": "scripts/connect/build_concept_index.py",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.parse_args()

    mtimes: dict[str, float | None] = {}
    for name, path, _ in CHAIN:
        mtimes[name] = path.stat().st_mtime if path.exists() else None

    stale: list[str] = []
    for name, path, deps in CHAIN:
        if mtimes[name] is None:
            if any(mtimes[d] is not None for d in deps):
                print(f"[missing] {name}: {path} 不存在(上游已就绪)", flush=True)
                stale.append(name)
            continue
        for d in deps:
            if mtimes[d] is not None and mtimes[d] > mtimes[name]:
                old = datetime.fromtimestamp(mtimes[name]).strftime("%m-%d %H:%M")
                new = datetime.fromtimestamp(mtimes[d]).strftime("%m-%d %H:%M")
                print(f"[stale] {name}({old}) 旧于上游 {d}({new})", flush=True)
                stale.append(name)
                break

    if not stale:
        print("freshness: OK(派生链全新鲜)", flush=True)
        return 0
    print("", flush=True)
    print("重建顺序(只跑过期的,按此序):", flush=True)
    for name, _, _ in CHAIN:
        if name in stale and name in REBUILD_HINT:
            print(f"  {REBUILD_HINT[name]}", flush=True)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
