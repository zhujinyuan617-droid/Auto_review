"""PDF 兜底拉机构(spec v2 既定方案,补建):无 DOI / OpenAlex 落空的论文,
用 AI 读首页版面块抽 作者+机构,写 authorship.json(source="pdf-ai"),
新机构追加进机构注册表(origin="pdf-ai",国别留给 enrich_institution_countries.py 补)。

用法(desktop_app/ 下,需 AUTOREVIEW_LIBRARY_DIR):
    .venv\\Scripts\\python scripts\\backfill_authorship_from_pdf.py [--dry-run]

范围:无 authorship.json,或有但全员零机构的论文。
前提:服务器此刻不得在跑 authorship populate(跨进程不护锁)。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

DESKTOP = Path(__file__).resolve().parents[1]
ROOT = DESKTOP.parent
sys.path.insert(0, str(DESKTOP / "src"))
sys.path.insert(0, str(ROOT / "Document_Decomposer" / "src"))

from autoreview_app.config import AppConfig  # noqa: E402
from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config  # noqa: E402

_SYSTEM = (
    "You read the first-page layout text of an academic paper and extract its authors "
    "and affiliations. Return faithful names exactly as printed (no translation). "
    "is_senior=true for the corresponding author (marked * or 'Corresponding') or, "
    "absent markers, the last author."
)
_HINT = (
    'Return only JSON: {"authors": [{"name": str, "is_senior": bool, '
    '"affiliations": [str]}]} where affiliations are full institution names '
    "(no addresses, no superscript letters). No Markdown."
)


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60] or "unknown"


def first_page_text(paper_dir: Path, max_blocks: int = 30) -> str:
    doc = json.loads((paper_dir / "content_blocks.json").read_text(encoding="utf-8"))
    out = []
    for b in doc.get("blocks") or []:
        if str(b.get("page_no")) == "1" and b.get("text"):
            out.append(str(b["text"]))
        if len(out) >= max_blocks:
            break
    return "\n".join(out)[:6000]


def needs_backfill(paper_dir: Path) -> bool:
    p = paper_dir / "authorship.json"
    if not p.exists():
        return True
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    return not any(a.get("institution_ids") for a in doc.get("authors") or [])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    cfg = AppConfig.from_env()
    reg_path = cfg.institutions_registry_path
    registry = json.loads(reg_path.read_text(encoding="utf-8"))
    entries = registry.setdefault("entries", {})
    by_name = {e["display_name"].strip().lower(): e["id"]
               for e in entries.values() if e.get("display_name")}

    ai = OpenAICompatibleClient(load_ai_config(ROOT / "Document_Decomposer", None))
    targets = [d.parent for d in sorted(cfg.library_dir.glob("*/literature_card.json"))
               if needs_backfill(d.parent)]
    print(f"[范围] {len(targets)} 篇待兜底:{[d.name for d in targets]}")
    done = failed = new_inst = 0
    for pd in targets:
        try:
            raw = ai.chat_json(
                [{"role": "system", "content": _SYSTEM},
                 {"role": "user", "content": first_page_text(pd)}], _HINT)
            authors_in = raw.get("authors") or []
            assert authors_in, "no authors extracted"
        except Exception as e:  # 单篇失败不挡批
            print(f"  [失败] {pd.name}: {e}")
            failed += 1
            continue
        authors = []
        for i, a in enumerate(authors_in):
            ids = []
            for aff in a.get("affiliations") or []:
                key = str(aff).strip().lower()
                if not key:
                    continue
                if key not in by_name:
                    eid = f"elem:institution/{_slug(aff)}"
                    if eid in entries:  # slug 撞名但显示名不同:挂同条目
                        by_name[key] = eid
                    else:
                        entries[eid] = {"id": eid, "facet": "institution",
                                        "display_name": str(aff).strip(), "aliases": [],
                                        "redirect_to": None, "origin": "pdf-ai",
                                        "human_locked": False}
                        by_name[key] = eid
                        new_inst += 1
                ids.append(by_name[key])
            authors.append({"name": str(a.get("name", "")).strip(), "position": i + 1,
                            "is_senior": bool(a.get("is_senior")),
                            "raw_affiliations": list(a.get("affiliations") or []),
                            "institution_ids": ids})
        doc = {"paper_id": pd.name, "authors": authors, "source": "pdf-ai",
               "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        print(f"  [完成] {pd.name}: {len(authors)} 作者, 机构 {sorted({i for a in authors for i in a['institution_ids']})}")
        if not args.dry_run:
            (pd / "authorship.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        done += 1
    if not args.dry_run and new_inst:
        tmp = reg_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(reg_path)
    print(f"[统计] 成功 {done} / 失败 {failed};新机构 {new_inst}(写回注册表={not args.dry_run})")
    if new_inst:
        print("[下一步] 跑 scripts/enrich_institution_countries.py 给新机构补国别,再 relayout institution 镜头")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
