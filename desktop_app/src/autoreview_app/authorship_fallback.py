"""导入链内建的作者机构兜底(用户拍板的分层方案):

卡片 AI 顺手抽的 `authors_raw`(首页署名照抄)→ 当 OpenAlex 路线缺席时
(无 authorship.json),落成 authorship.json(source="card-ai"),
新机构追加进机构注册表(origin="card-ai",国别留给补查脚本)。

口径:OpenAlex 有 DOI 时仍为准(批量 populate 会覆盖 card-ai?不——populate
只补缺失,不覆盖已有;card-ai 先到先得,质量以人工抽样把关)。
写注册表必须持 INSTITUTIONS_REGISTRY_LOCK(进程内锁,见 registry_locks.py)。
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .registry_locks import INSTITUTIONS_REGISTRY_LOCK


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s[:60] or "unknown"


def authorship_from_card(paper_dir: Path, registry_path: Path) -> bool:
    """有 authors_raw 且无 authorship.json 时落兜底;返回是否写了。"""
    out_path = paper_dir / "authorship.json"
    if out_path.exists():
        return False
    try:
        card = json.loads((paper_dir / "literature_card.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    authors_raw = card.get("authors_raw") or []
    if not authors_raw:
        return False

    with INSTITUTIONS_REGISTRY_LOCK:
        try:
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            registry = {"schema_version": "0.1.0", "facets": ["institution"], "entries": {}}
        entries = registry.setdefault("entries", {})
        by_name = {e["display_name"].strip().lower(): e["id"]
                   for e in entries.values() if e.get("display_name")}
        authors = []
        new_inst = 0
        for i, a in enumerate(authors_raw):
            ids = []
            for aff in a.get("affiliations") or []:
                key = str(aff).strip().lower()
                if not key:
                    continue
                if key not in by_name:
                    eid = f"elem:institution/{_slug(aff)}"
                    if eid not in entries:
                        entries[eid] = {"id": eid, "facet": "institution",
                                        "display_name": str(aff).strip(), "aliases": [],
                                        "redirect_to": None, "origin": "card-ai",
                                        "human_locked": False}
                        new_inst += 1
                    by_name[key] = eid
                ids.append(by_name[key])
            authors.append({"name": str(a.get("name", "")).strip(), "position": i + 1,
                            "is_senior": bool(a.get("is_senior")),
                            "raw_affiliations": list(a.get("affiliations") or []),
                            "institution_ids": ids})
        if new_inst:
            registry_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = registry_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(registry, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(registry_path)

    doc = {"paper_id": paper_dir.name, "authors": authors, "source": "card-ai",
           "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return True
