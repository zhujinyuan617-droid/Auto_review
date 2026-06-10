"""Desktop wrapper over the engine's element modules.

All engine logic stays in Document_Decomposer (docdecomp.element_*); this module
only wires paths/config and composes the per-paper and bootstrap flows.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

from .. import engine_bridge

engine_bridge.ensure_engine_scripts_on_path()

from docdecomp.card_tags import (  # noqa: E402
    apply_derived_tags,
    derive_classification,
    derive_topic_ids,
)
from docdecomp.element_bootstrap import bootstrap_registry, superbucket_report  # noqa: E402
from docdecomp.element_extraction import run_element_extraction  # noqa: E402
from docdecomp.element_index import build_index  # noqa: E402
from docdecomp.element_matching import bulk_match_elements, match_paper_elements  # noqa: E402
from docdecomp.element_registry import (  # noqa: E402
    load_registry,
    load_seeds,
    new_registry_from_seeds,
    save_registry,
)
from docdecomp.io_utils import write_json  # noqa: E402

from ..config import AppConfig  # noqa: E402

Report = Callable[[str], None]


def engine_root() -> Path:
    return engine_bridge.ENGINE_SCRIPTS.parent


def seeds_path() -> Path:
    return engine_root() / "config" / "element_seeds.json"


def ensure_registry(config: AppConfig) -> dict:
    if config.elements_registry_path.exists():
        return load_registry(config.elements_registry_path)
    registry = new_registry_from_seeds(load_seeds(seeds_path()))
    config.elements_data_dir.mkdir(parents=True, exist_ok=True)
    save_registry(config.elements_registry_path, registry)
    return registry


def _derive_tags_for_paper(paper_dir: Path, registry: dict) -> bool:
    """Derive and write card_tags for a single paper. Returns True if card was written."""
    elements_path = paper_dir / "elements.json"
    card_path = paper_dir / "literature_card.json"
    if not elements_path.exists() or not card_path.exists():
        return False
    elements_doc = json.loads(elements_path.read_text(encoding="utf-8"))
    card = json.loads(card_path.read_text(encoding="utf-8"))
    derived = derive_classification(elements_doc, registry)
    apply_derived_tags(card, derived)
    card.setdefault("classification", {})["topic_ids"] = derive_topic_ids(card, registry)
    write_json(card_path, card)
    return True


def run_elements_for_paper(paper_dir: Path, client: Any, config: AppConfig,
                           report: Report = lambda m: None) -> dict:
    seeds = load_seeds(seeds_path())
    report("extracting elements")
    result = run_element_extraction(paper_dir, client, seeds)
    registry = ensure_registry(config)
    report("matching elements against registry")
    match_paper_elements(paper_dir, registry, client, config.elements_log_path)
    save_registry(config.elements_registry_path, registry)
    report("updating elements index")
    build_index(config.library_dir, registry, config.elements_db)
    card_path = paper_dir / "literature_card.json"
    if card_path.exists():
        report("deriving card tags")
        try:
            _derive_tags_for_paper(paper_dir, registry)
        except Exception as exc:  # noqa: BLE001 — 单篇失败不挡导入
            report(f"{paper_dir.name} tag derivation failed: {type(exc).__name__}")
    return {"occurrences": len(result["occurrences"]), "dropped": len(result["dropped"])}


def list_paper_dirs(config: AppConfig) -> list[Path]:
    return [p.parent for p in sorted(config.library_dir.glob("*/reading_blocks.json"))]


def coverage(config: AppConfig) -> dict:
    papers = list_paper_dirs(config)
    pending = [p.name for p in papers if not (p / "elements.json").exists()]
    deferred = [p.parent.name for p in sorted(config.library_dir.glob("*/language_gate.json"))]
    return {"papers": len(papers), "with_elements": len(papers) - len(pending),
            "pending": pending, "deferred": deferred}


def run_bootstrap(config: AppConfig, client: Any, report: Report = lambda m: None,
                  parallel: int = 6) -> dict:
    """First run: extract missing -> ONE-TIME consolidation -> index.

    Later runs (registry already exists): extract missing + stream-match only —
    NEVER re-consolidates, so the registry stays frozen (anti-I12 drift). This
    also doubles as the "retry pending papers" action: re-clicking the build
    button tops up coverage incrementally.

    parallel: number of ThreadPool workers for the extraction phase (default 6).
    JobRegistry.report appends under a lock, so calling report() from worker
    threads is safe.
    """
    seeds = load_seeds(seeds_path())
    papers = list_paper_dirs(config)
    pending = [p for p in papers if not (p / "elements.json").exists()]
    extracted = failed = 0

    if parallel <= 1 or len(pending) <= 1:
        # Serial path
        for paper_dir in pending:
            try:
                report(f"extracting {paper_dir.name}")
                run_element_extraction(paper_dir, client, seeds)
                extracted += 1
            except Exception as exc:  # noqa: BLE001 — 单篇失败不挡全局, 留待补
                failed += 1
                report(f"{paper_dir.name} failed: {type(exc).__name__}")
    else:
        # Parallel extraction — one shared client (stateless per-call, house-proven safe)
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            fut_to_dir = {
                pool.submit(run_element_extraction, paper_dir, client, seeds): paper_dir
                for paper_dir in pending
            }
            for fut in as_completed(fut_to_dir):
                paper_dir = fut_to_dir[fut]
                try:
                    fut.result()
                    extracted += 1
                    report(f"extracted {paper_dir.name}")
                except Exception as exc:  # noqa: BLE001
                    failed += 1
                    report(f"{paper_dir.name} failed: {type(exc).__name__}")

    config.elements_data_dir.mkdir(parents=True, exist_ok=True)
    if config.elements_registry_path.exists():
        report("registry exists: bulk-matching all papers (no re-consolidation)")
        registry = load_registry(config.elements_registry_path)
        # 判同并行(只读提案);落账在 bulk 内部串行 —— 单写入者不变,勿再并行化落账
        papers_with_elements = [p for p in papers if (p / "elements.json").exists()]
        bstats = bulk_match_elements(
            papers_with_elements, registry, client, config.elements_log_path,
            parallel=parallel)
        report(
            f"bulk match: groups={bstats['groups_total']} ai_calls={bstats['ai_calls']} "
            f"created={bstats['created']} failed_chunks={bstats['judge_failed_chunks']}")
        save_registry(config.elements_registry_path, registry)
    else:
        report("consolidating registry (one-time)")
        registry = bootstrap_registry(config.library_dir, seeds, client,
                                      config.elements_data_dir, progress=report)
    n = build_index(config.library_dir, registry, config.elements_db)
    flagged = superbucket_report(registry)

    report("deriving card tags for all papers")
    for paper_dir in papers:
        try:
            _derive_tags_for_paper(paper_dir, registry)
        except Exception as exc:  # noqa: BLE001 — 单篇失败不挡全局
            report(f"{paper_dir.name} tag derivation failed: {type(exc).__name__}")

    report(f"done: index over {n} papers; {len(flagged)} superbucket flags")
    return {"papers_indexed": n, "extracted": extracted, "extract_failed": failed,
            "entries": len(registry["entries"]), "superbuckets": flagged}
