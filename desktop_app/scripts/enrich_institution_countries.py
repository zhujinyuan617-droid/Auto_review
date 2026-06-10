"""一次性国别补查(Wave-3 ④ 前置):机构注册表 → OpenAlex → country_code。

用法(desktop_app/ 下):
    .venv\\Scripts\\python scripts\\enrich_institution_countries.py [--force] [--dry-run]

- 数据源:GET https://api.openalex.org/institutions?search=<名称>&per-page=1
  (按名搜索取首个命中;注册表里没有存 OpenAlex ID,这是唯一可用的口径)。
- 写回字段(append-only):country_code / openalex_id / openalex_match_name /
  country_source="openalex-search";已有 country_code 的条目默认跳过(--force 重查)。
- 诚实声明:按名搜索的首个命中可能错配,openalex_match_name 留底供人工核对;
  本脚本只补国别,不动 display_name/aliases/redirect。
- 运行前提:桌面服务此刻不得在跑 authorship populate(两边都会写注册表;
  registry_locks 是进程内锁,跨进程不护)。
- AUTOREVIEW_MAILTO 环境变量若存在则附给 OpenAlex(polite pool 提速),不强制。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from autoreview_app.config import AppConfig  # noqa: E402

OPENALEX = "https://api.openalex.org/institutions"


def openalex_lookup(name: str, mailto: str | None = None, retries: int = 3) -> dict | None:
    """按名称搜索 OpenAlex 机构,返回首个命中 {id, display_name, country_code} 或 None。"""
    params = {"search": name, "per-page": "1", "select": "id,display_name,country_code"}
    if mailto:
        params["mailto"] = mailto
    url = f"{OPENALEX}?{urllib.parse.urlencode(params)}"
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            results = data.get("results") or []
            return results[0] if results else None
        except Exception:  # 网络抖动/429:退避重试,最后一跳放弃该条
            if attempt == retries - 1:
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def enrich_registry(registry: dict, lookup, force: bool = False) -> dict:
    """对缺 country_code 的条目逐个补查;lookup 可注入(测试不联网)。返回统计。"""
    stats = {"total": 0, "skipped": 0, "matched": 0, "no_hit": 0, "no_country": 0}
    for entry in (registry.get("entries") or {}).values():
        if entry.get("redirect_to"):
            continue
        stats["total"] += 1
        if entry.get("country_code") and not force:
            stats["skipped"] += 1
            continue
        hit = lookup(entry.get("display_name") or "")
        if not hit:
            stats["no_hit"] += 1
            continue
        cc = hit.get("country_code")
        entry["openalex_id"] = hit.get("id")
        entry["openalex_match_name"] = hit.get("display_name")
        entry["country_source"] = "openalex-search"
        if cc:
            entry["country_code"] = str(cc).upper()
            stats["matched"] += 1
        else:
            stats["no_country"] += 1
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--force", action="store_true", help="已有 country_code 的也重查")
    ap.add_argument("--dry-run", action="store_true", help="只查不写盘")
    args = ap.parse_args()

    cfg = AppConfig.from_env()
    path = cfg.institutions_registry_path
    if not path.is_file():
        print(f"[错误] 机构注册表不存在:{path}")
        return 1
    registry = json.loads(path.read_text(encoding="utf-8"))
    mailto = os.environ.get("AUTOREVIEW_MAILTO")
    print(f"[开始] {path};mailto={'有' if mailto else '无(公共池)'}")

    done = {"n": 0}

    def lookup(name: str):
        done["n"] += 1
        if done["n"] % 25 == 0:
            print(f"  …已查 {done['n']} 家")
        return openalex_lookup(name, mailto)

    stats = enrich_registry(registry, lookup, force=args.force)
    print(f"[统计] 条目 {stats['total']}(跳过已有 {stats['skipped']});"
          f"命中国别 {stats['matched']},搜索无命中 {stats['no_hit']},命中但无国别 {stats['no_country']}")
    if args.dry_run:
        print("[dry-run] 不写盘")
        return 0
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    print(f"[完成] 已写回 {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
