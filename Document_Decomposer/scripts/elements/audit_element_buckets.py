"""Report oversized registry entries (possible over-merge; see ISSUES I12)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from docdecomp.element_bootstrap import superbucket_report  # noqa: E402
from docdecomp.element_registry import load_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "elements"))
    ap.add_argument("--max-aliases", type=int, default=12)
    args = ap.parse_args()
    registry = load_registry(Path(args.data_dir) / "registry.json")
    flagged = superbucket_report(registry, max_aliases=args.max_aliases)
    for f in flagged:
        print(f"{f['id']}  aliases={f['alias_count']}  ({f['display_name']})", flush=True)
    print(f"total flagged: {len(flagged)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
