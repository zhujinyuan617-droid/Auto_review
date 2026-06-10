"""Desktop wrapper over the engine's element modules.

All engine logic stays in Document_Decomposer (docdecomp.element_*); this module
only wires paths/config and composes the per-paper and bootstrap flows.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .. import engine_bridge

engine_bridge.ensure_engine_scripts_on_path()

from docdecomp.element_bootstrap import bootstrap_registry, superbucket_report  # noqa: E402
from docdecomp.element_extraction import run_element_extraction  # noqa: E402
from docdecomp.element_index import build_index  # noqa: E402
from docdecomp.element_matching import match_paper_elements  # noqa: E402
from docdecomp.element_registry import (  # noqa: E402
    load_registry,
    load_seeds,
    new_registry_from_seeds,
    save_registry,
)

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
    return {"occurrences": len(result["occurrences"]), "dropped": len(result["dropped"])}


def list_paper_dirs(config: AppConfig) -> list[Path]:
    return [p.parent for p in sorted(config.library_dir.glob("*/reading_blocks.json"))]


def coverage(config: AppConfig) -> dict:
    papers = list_paper_dirs(config)
    pending = [p.name for p in papers if not (p / "elements.json").exists()]
    deferred = [p.parent.name for p in sorted(config.library_dir.glob("*/language_gate.json"))]
    return {"papers": len(papers), "with_elements": len(papers) - len(pending),
            "pending": pending, "deferred": deferred}


def run_bootstrap(config: AppConfig, client: Any, report: Report = lambda m: None) -> dict:
    """First run: extract missing -> ONE-TIME consolidation -> index.

    Later runs (registry already exists): extract missing + stream-match only —
    NEVER re-consolidates, so the registry stays frozen (anti-I12 drift). This
    also doubles as the "retry pending papers" action: re-clicking the build
    button tops up coverage incrementally.
    """
    seeds = load_seeds(seeds_path())
    papers = list_paper_dirs(config)
    extracted = failed = 0
    for paper_dir in papers:
        if (paper_dir / "elements.json").exists():
            continue
        try:
            report(f"extracting {paper_dir.name}")
            run_element_extraction(paper_dir, client, seeds)
            extracted += 1
        except Exception as exc:  # noqa: BLE001 — 单篇失败不挡全局, 留待补
            failed += 1
            report(f"{paper_dir.name} failed: {type(exc).__name__}")
    config.elements_data_dir.mkdir(parents=True, exist_ok=True)
    if config.elements_registry_path.exists():
        report("registry exists: stream-matching all papers (no re-consolidation)")
        registry = load_registry(config.elements_registry_path)
        for paper_dir in papers:
            if (paper_dir / "elements.json").exists():
                match_paper_elements(paper_dir, registry, client, config.elements_log_path)
        save_registry(config.elements_registry_path, registry)
    else:
        report("consolidating registry (one-time)")
        registry = bootstrap_registry(config.library_dir, seeds, client,
                                      config.elements_data_dir, progress=report)
    n = build_index(config.library_dir, registry, config.elements_db)
    flagged = superbucket_report(registry)
    report(f"done: index over {n} papers; {len(flagged)} superbucket flags")
    return {"papers_indexed": n, "extracted": extracted, "extract_failed": failed,
            "entries": len(registry["entries"]), "superbuckets": flagged}
