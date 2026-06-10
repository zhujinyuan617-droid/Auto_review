"""Auto-merge registry entries whose display_name norm_keys are identical (same facet).

审计 I21 的"该并未并"硬重复(isotherm/isotherms 这类归一后同形的条目)由本脚本机械收口:
merge = redirect(条目永不删除)。目标选择:human_locked > seed > 别名多者 > id 字典序小;
human_locked 条目绝不作 from 端;两条都锁 → 留给人裁。默认 --dry-run 只报告,--apply 才落账。

提醒(ISSUES I18):apply 之后派生物过期,须重跑 card_tags 回填 + derive_vocabulary。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.element_registry import (  # noqa: E402
    load_registry,
    merge_entries,
    norm_key,
    save_registry,
)


def _singularize_token(token: str) -> str:
    """保守去复数:仅剥词尾单个 s;短词(≤3)与 ss/us/is 结尾不动(gas/glass/basis 安全)。"""
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
        return token[:-1]
    return token


def dedupe_key(name: str) -> str:
    """norm_key + 逐词保守复数折叠——isotherm/isotherms、Materials/Material Studio 同键。"""
    return " ".join(_singularize_token(t) for t in norm_key(name).split())


def find_duplicate_groups(registry: dict) -> dict[tuple[str, str], list[dict]]:
    """(facet, dedupe_key(display_name)) 完全相同的非 redirect 条目组(组内 ≥2)。"""
    groups: dict[tuple[str, str], list[dict]] = {}
    for entry in registry["entries"].values():
        if entry.get("redirect_to"):
            continue
        key = (entry["facet"], dedupe_key(entry["display_name"]))
        groups.setdefault(key, []).append(entry)
    return {k: v for k, v in groups.items() if len(v) > 1}


def pick_target(members: list[dict]) -> dict:
    """合并目标:human_locked > origin==seed > 别名多者 > id 小者。"""
    return sorted(
        members,
        key=lambda e: (
            not e.get("human_locked", False),
            e.get("origin") != "seed",
            -len(e.get("aliases") or []),
            e["id"],
        ),
    )[0]


def merge_duplicates(registry: dict, log_path: Path, apply: bool) -> dict:
    stats = {"groups": 0, "merged": 0, "skipped_locked": 0}
    for (facet, key), members in sorted(find_duplicate_groups(registry).items()):
        stats["groups"] += 1
        target = pick_target(members)
        for entry in sorted(members, key=lambda e: e["id"]):
            if entry["id"] == target["id"]:
                continue
            if entry.get("human_locked", False):
                stats["skipped_locked"] += 1
                print(f"  [locked] {facet}/{key}: {entry['id']} 与 {target['id']} 同形但人工锁定,留给人裁", flush=True)
                continue
            print(f"  {'merge' if apply else 'would-merge'} {entry['id']} -> {target['id']}", flush=True)
            if apply:
                merge_entries(registry, entry["id"], target["id"], "auto-dedupe", log_path)
                stats["merged"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "elements"),
                    help="directory containing registry.json (default: ROOT/data/elements)")
    ap.add_argument("--apply", action="store_true",
                    help="actually merge and save; default is dry-run report")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    registry_path = data_dir / "registry.json"
    log_path = data_dir / "registry_log.jsonl"
    if not registry_path.exists():
        print(f"[error] registry.json not found at {registry_path}", file=sys.stderr, flush=True)
        return 1

    registry = load_registry(registry_path)
    stats = merge_duplicates(registry, log_path, apply=args.apply)
    if args.apply and stats["merged"]:
        save_registry(registry_path, registry)
        print("REMINDER (I18): now rerun card_tags backfill + derive_vocabulary.", flush=True)
    print(
        f"normkey-dedupe: groups={stats['groups']} merged={stats['merged']} "
        f"skipped_locked={stats['skipped_locked']} mode={'apply' if args.apply else 'dry-run'}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
