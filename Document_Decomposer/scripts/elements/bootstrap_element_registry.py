"""One-time bootstrap: consolidate all extracted surfaces -> registry v1 + index.

Run ai_extract_elements.py first (this script consolidates, it does not extract).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config  # noqa: E402
from docdecomp.element_bootstrap import bootstrap_registry, superbucket_report  # noqa: E402
from docdecomp.element_index import build_index  # noqa: E402
from docdecomp.element_registry import load_seeds  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "elements"))
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    if (data_dir / "registry.json").exists():
        print("registry.json already exists; bootstrap is one-time. "
              "Delete it deliberately if you really mean to redo (human edits in the "
              "log are replayable, but think first).", flush=True)
        return 1
    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)
    seeds = load_seeds(ROOT / "config" / "element_seeds.json")
    registry = bootstrap_registry(Path(args.library_dir), seeds, client, data_dir,
                                  progress=lambda m: print(m, flush=True))
    n = build_index(Path(args.library_dir), registry, data_dir / "elements_index.sqlite")
    print(f"registry: {len(registry['entries'])} entries; index over {n} papers", flush=True)
    flagged = superbucket_report(registry)
    for f in flagged:
        print(f"[superbucket?] {f['id']} aliases={f['alias_count']}", flush=True)
    print(f"superbuckets flagged: {len(flagged)} (review manually if >0)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
