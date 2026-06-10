"""Append missing mechanism/phenomenon topic tags to existing literature cards.

审计 I20 续(2026-06-10 抽样):27% 论文的 domain_tags 只有储层/场景词,漏了标题里的
机制词(confinement/phase behavior/gas transport...)。本脚本对存量卡做**追加式**补标:
AI 只回"缺失的机制/现象标签"(0-3 个),绝不改动已有标签;打 `mechanism_enriched`
标记保证幂等。跑完须接 resolve_topics_bulk(新标签→topic_ids)+ derive_vocabulary。
"""
from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config  # noqa: E402
from docdecomp.io_utils import write_json  # noqa: E402

_SYSTEM = (
    "You add MISSING mechanism/phenomenon topic tags to a literature index card. "
    "Given the title, objective, findings and current tags, return 0-3 SHORT normalized "
    "lowercase tags naming the core mechanisms or phenomena the paper STUDIES "
    "(e.g. adsorption, diffusion, confinement effect, phase behavior, gas transport, "
    "competitive adsorption). Rules: only mechanisms actually studied (not merely "
    "mentioned); never repeat or rephrase an existing tag; reservoir/scenario types "
    "(shale gas, unconventional reservoirs) are NOT mechanisms; return an empty list "
    "when nothing is missing."
)
_HINT = 'Return only one JSON object: {"add_tags": [string]}. Do not wrap in Markdown.'

MAX_TOTAL_TAGS = 9


def merge_tags(card: dict, add_tags: list) -> int:
    """追加去重(按小写比对),总数封顶;返回实际新增数。纯函数便于测试。"""
    cls = card.setdefault("classification", {})
    tags = [str(t) for t in (cls.get("domain_tags") or [])]
    seen = {t.strip().lower() for t in tags}
    added = 0
    for raw in add_tags or []:
        t = str(raw).strip()
        if not t or t.lower() in seen or len(tags) >= MAX_TOTAL_TAGS:
            continue
        tags.append(t)
        seen.add(t.lower())
        added += 1
    cls["domain_tags"] = tags
    return added


def enrich_paper(paper_dir: Path, client) -> dict:
    card_path = paper_dir / "literature_card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    cls = card.setdefault("classification", {})
    if cls.get("mechanism_enriched"):
        return {"paper": paper_dir.name, "added": 0, "skipped": True}
    summary = card.get("summary") or {}
    payload = {
        "title": (card.get("paper") or {}).get("title") or "",
        "objective": summary.get("objective") or "",
        "main_findings": summary.get("main_findings") or [],
        "current_tags": cls.get("domain_tags") or [],
    }
    raw = client.chat_json(
        [{"role": "system", "content": _SYSTEM},
         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        _HINT,
    )
    added = merge_tags(card, raw.get("add_tags") or [])
    cls["mechanism_enriched"] = True
    write_json(card_path, card)
    return {"paper": paper_dir.name, "added": added, "skipped": False}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--paper", default=None, help="single paper id; default: all un-enriched")
    ap.add_argument("--parallel", type=int, default=32)
    args = ap.parse_args()

    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)
    library = Path(args.library_dir)
    if args.paper:
        targets = [library / args.paper]
    else:
        targets = [p.parent for p in sorted(library.glob("*/literature_card.json"))]

    ok = failed = added_total = skipped = 0
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futs = {pool.submit(enrich_paper, d, client): d for d in targets}
        for fut in as_completed(futs):
            d = futs[fut]
            try:
                r = fut.result()
                ok += 1
                added_total += r["added"]
                skipped += int(r["skipped"])
                if r["added"]:
                    print(f"[{d.name}] +{r['added']} mechanism tags", flush=True)
            except Exception as exc:  # noqa: BLE001 — 单篇失败不挡全批
                failed += 1
                print(f"[{d.name}] FAILED: {type(exc).__name__}: {exc}", flush=True)

    print(f"done: {ok} ok ({skipped} already-enriched), {failed} failed, "
          f"+{added_total} tags total", flush=True)
    print("REMINDER: now run resolve_topics_bulk + derive_vocabulary (+freshness gate).", flush=True)
    print("DEPENDENCY: rerunning the card stage OVERWRITES enriched tags and the "
          "mechanism_enriched marker — after any card rerun, rerun this script "
          "AND card_tags backfill (opus review I-1).", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
