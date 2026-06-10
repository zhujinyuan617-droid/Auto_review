"""Extract research elements for one paper or all papers missing elements.json."""
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
from docdecomp.element_extraction import run_element_extraction  # noqa: E402
from docdecomp.element_registry import load_seeds  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--paper", default=None, help="one paper id (e.g. S09); default: all missing")
    ap.add_argument("--force", action="store_true", help="re-extract even if elements.json exists")
    ap.add_argument("--parallel", type=int, default=6,
                    help="number of parallel extraction workers (default: 6; 1 = serial)")
    args = ap.parse_args()

    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    # One shared client across threads — the house pattern (run_from_paper_downloads.py)
    # already proves this safe: OpenAICompatibleClient is stateless per-call.
    client = OpenAICompatibleClient(config)
    seeds = load_seeds(ROOT / "config" / "element_seeds.json")
    library = Path(args.library_dir)

    if args.paper:
        targets = [library / args.paper]
    else:
        targets = [p.parent for p in sorted(library.glob("*/reading_blocks.json"))
                   if args.force or not (p.parent / "elements.json").exists()]

    ok = failed = 0

    if args.parallel <= 1 or len(targets) <= 1:
        # Serial path — no ThreadPool overhead
        for paper_dir in targets:
            try:
                result = run_element_extraction(paper_dir, client, seeds)
                ok += 1
                print(f"[{paper_dir.name}] {len(result['occurrences'])} occurrences, "
                      f"{len(result['dropped'])} dropped", flush=True)
            except Exception as exc:  # noqa: BLE001 — batch keeps going, summary at end
                failed += 1
                print(f"[{paper_dir.name}] FAILED: {type(exc).__name__}: {exc}", flush=True)
    else:
        # Parallel path — ThreadPool per house pattern
        with ThreadPoolExecutor(max_workers=args.parallel) as pool:
            fut_to_dir = {
                pool.submit(run_element_extraction, paper_dir, client, seeds): paper_dir
                for paper_dir in targets
            }
            for fut in as_completed(fut_to_dir):
                paper_dir = fut_to_dir[fut]
                try:
                    result = fut.result()
                    ok += 1
                    print(f"[{paper_dir.name}] {len(result['occurrences'])} occurrences, "
                          f"{len(result['dropped'])} dropped", flush=True)
                except Exception as exc:  # noqa: BLE001 — batch keeps going, summary at end
                    failed += 1
                    print(f"[{paper_dir.name}] FAILED: {type(exc).__name__}: {exc}", flush=True)

    print(f"done: {ok} ok, {failed} failed of {len(targets)}", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
