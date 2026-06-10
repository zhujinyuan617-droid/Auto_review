"""Idempotent parallel backfill of 'finding' occurrences for papers that already have elements.json.

Phase A: for each target paper, call AI (_FINDING_SYSTEM) to re-extract findings,
         replace any existing finding occurrences, and write elements.json.
Phase B: if registry.json exists in --data-dir, re-run match_paper_elements +
         rebuild the SQLite index so canonical_ids are populated.

Targets: all papers WITH elements.json (or a single paper via --paper).
Safe to run repeatedly — idempotent by design.
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config  # noqa: E402
from docdecomp.element_extraction import backfill_findings  # noqa: E402
from docdecomp.element_index import build_index  # noqa: E402
from docdecomp.element_matching import bulk_match_elements, match_paper_elements  # noqa: E402
from docdecomp.element_registry import load_registry, load_seeds, save_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"),
                    help="path to the library directory (default: <repo>/library)")
    ap.add_argument("--config", default=None,
                    help="path to AI config JSON (default: auto-detect)")
    ap.add_argument("--paper", default=None,
                    help="single paper id (e.g. S09); default: all papers with elements.json")
    ap.add_argument("--parallel", type=int, default=6,
                    help="parallel extraction workers (default: 6; 1 = serial)")
    ap.add_argument("--match-mode", choices=["bulk", "stream"], default="bulk",
                    help="phase-B normalization: bulk (parallel judging, default) or legacy per-paper stream")
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "elements"),
                    help="directory for registry.json + index.db (default: <repo>/data/elements)")
    args = ap.parse_args()

    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    # One shared client across threads (house pattern — stateless per-call).
    client = OpenAICompatibleClient(config)
    seeds = load_seeds(ROOT / "config" / "element_seeds.json")
    library = Path(args.library_dir)
    data_dir = Path(args.data_dir)

    # Collect targets: papers that already have elements.json.
    if args.paper:
        targets = [library / args.paper]
    else:
        targets = [p.parent for p in sorted(library.glob("*/elements.json"))]

    if not targets:
        print("No target papers found — nothing to do.", flush=True)
        return 0

    # ------------------------------------------------------------------
    # Phase A: extraction (serial or ThreadPool)
    # ------------------------------------------------------------------
    ok: list[Path] = []
    failed: list[Path] = []

    def _run(paper_dir: Path) -> dict:
        return backfill_findings(paper_dir, client, seeds)

    if args.parallel <= 1 or len(targets) <= 1:
        for paper_dir in targets:
            try:
                stats = _run(paper_dir)
                ok.append(paper_dir)
                print(
                    f"[{paper_dir.name}] +{stats['added']} findings "
                    f"({stats['removed_old']} removed, {stats['dropped']} dropped)",
                    flush=True,
                )
            except Exception as exc:  # noqa: BLE001 — batch keeps going
                failed.append(paper_dir)
                print(f"[{paper_dir.name}] FAILED: {type(exc).__name__}: {exc}", flush=True)
    else:
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            fut_to_dir = {pool.submit(_run, paper_dir): paper_dir for paper_dir in targets}
            for fut in as_completed(fut_to_dir):
                paper_dir = fut_to_dir[fut]
                try:
                    stats = fut.result()
                    ok.append(paper_dir)
                    print(
                        f"[{paper_dir.name}] +{stats['added']} findings "
                        f"({stats['removed_old']} removed, {stats['dropped']} dropped)",
                        flush=True,
                    )
                except Exception as exc:  # noqa: BLE001 — batch keeps going
                    failed.append(paper_dir)
                    print(f"[{paper_dir.name}] FAILED: {type(exc).__name__}: {exc}", flush=True)

    # ------------------------------------------------------------------
    # Phase B: re-match + reindex (serial, only if registry exists)
    # ------------------------------------------------------------------
    registry_path = data_dir / "registry.json"
    db_path = data_dir / "index.db"
    log_path = data_dir / "element_events.log"

    if registry_path.exists() and ok:
        registry = load_registry(registry_path)
        if args.match_mode == "bulk":
            all_papers = [p.parent for p in sorted(library.glob("*/elements.json"))]
            mstats = bulk_match_elements(
                all_papers, registry, client, log_path, parallel=args.parallel)
            print(
                f"bulk match: groups={mstats['groups_total']} "
                f"ai_calls={mstats['ai_calls']} created={mstats['created']} "
                f"failed_chunks={mstats['judge_failed_chunks']} "
                f"papers_written={mstats['papers_written']}",
                flush=True,
            )
        else:
            matched = 0
            for paper_dir in ok:
                try:
                    match_paper_elements(paper_dir, registry, client, log_path)
                    matched += 1
                except Exception as exc:  # noqa: BLE001
                    print(f"[{paper_dir.name}] match FAILED: {type(exc).__name__}: {exc}", flush=True)
            print(f"stream match: {matched} papers re-matched", flush=True)
        save_registry(registry_path, registry)
        n_papers = build_index(library, registry, db_path)
        print(f"registry saved; index rebuilt over {n_papers} papers", flush=True)
    elif not registry_path.exists():
        print(
            f"WARNING: no registry found at {registry_path}; canonical_id left null. "
            "Run bootstrap_element_registry.py + ai_extract_elements.py --force first.",
            flush=True,
        )

    print(
        f"done: {len(ok)} ok, {len(failed)} failed of {len(targets)}",
        flush=True,
    )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
