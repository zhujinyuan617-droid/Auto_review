"""Rebuild data/elements/elements_index.sqlite from elements.json files + registry."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.element_index import build_index  # noqa: E402
from docdecomp.element_registry import load_registry  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--data-dir", default=str(ROOT / "data" / "elements"))
    args = ap.parse_args()
    data_dir = Path(args.data_dir)
    registry = load_registry(data_dir / "registry.json")
    n = build_index(Path(args.library_dir), registry, data_dir / "elements_index.sqlite")
    print(f"index rebuilt over {n} papers", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
