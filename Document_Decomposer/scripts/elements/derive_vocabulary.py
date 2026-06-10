"""Derive vocabulary.json from the element registry (replaces AI-normalisation step).

Core logic lives in src/docdecomp/derive_vocabulary.py for unit-testability.

Facet mapping:
  topic  ← registry topic
  method ← registry preparation + measurement + simulation
  object ← registry material

Backup behaviour: if --out exists and no sibling vocabulary.pre_derive.json exists,
copy out → backup first (never overwrite an existing backup).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.derive_vocabulary import derive_vocabulary  # noqa: E402
from docdecomp.element_registry import load_registry  # noqa: E402
from docdecomp.io_utils import write_json  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--data-dir",
        default=str(ROOT / "data" / "elements"),
        help="Directory containing registry.json (default: ROOT/data/elements)",
    )
    ap.add_argument(
        "--library-dir",
        default=str(ROOT / "library"),
        help="Root library directory for counting literature_card.json files (default: ROOT/library)",
    )
    ap.add_argument(
        "--out",
        default=str(ROOT / "reports" / "connection" / "vocabulary.json"),
        help="Output path for vocabulary.json (default: ROOT/reports/connection/vocabulary.json)",
    )
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    library_dir = Path(args.library_dir)
    out_path = Path(args.out)
    registry_path = data_dir / "registry.json"

    if not registry_path.exists():
        print(
            f"[error] registry.json not found at {registry_path}.",
            file=sys.stderr,
            flush=True,
        )
        return 1

    registry = load_registry(registry_path)

    # Count literature cards
    card_count = len(list(library_dir.glob("*/literature_card.json")))

    # Backup: if out exists and no pre_derive backup yet, create it
    backup_path = out_path.parent / "vocabulary.pre_derive.json"
    if out_path.exists() and not backup_path.exists():
        shutil.copy2(out_path, backup_path)
        print(f"[backup] {out_path.name} → {backup_path.name}", flush=True)

    vocab = derive_vocabulary(registry, card_count=card_count)
    write_json(out_path, vocab)

    topic_count = len(vocab["facets"]["topic"]["concepts"])
    method_count = len(vocab["facets"]["method"]["concepts"])
    object_count = len(vocab["facets"]["object"]["concepts"])
    warn_count = len(vocab.get("warnings") or [])

    print(
        f"derive_vocabulary: card_count={card_count} "
        f"topic={topic_count} method={method_count} object={object_count} "
        f"warnings={warn_count}",
        flush=True,
    )
    for w in (vocab.get("warnings") or []):
        print(f"  [warn] {w}", flush=True)

    print(f"written → {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
