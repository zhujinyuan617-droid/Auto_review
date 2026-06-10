"""Seed the element registry with topic concepts from a legacy vocabulary.json.

For each concept in vocabulary.facets.topic.concepts:
  - If canonical already exists as a registry topic entry → skip (idempotent).
  - Otherwise → create_entry(origin="seed").
  - For each member != canonical → add_alias (idempotent via norm_key guard).

Idempotent: re-running prints created=0.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import json  # noqa: E402

from docdecomp.element_registry import (  # noqa: E402
    add_alias,
    create_entry,
    find_by_surface,
    load_registry,
    save_registry,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--vocab",
        default=str(ROOT / "reports" / "connection" / "vocabulary.json"),
        help="Path to vocabulary.json (default: ROOT/reports/connection/vocabulary.json)",
    )
    ap.add_argument(
        "--data-dir",
        default=str(ROOT / "data" / "elements"),
        help="Directory containing registry.json (default: ROOT/data/elements)",
    )
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    registry_path = data_dir / "registry.json"
    if not registry_path.exists():
        print(
            f"[error] registry.json not found at {registry_path}. "
            "Run bootstrap_element_registry.py first.",
            file=sys.stderr,
            flush=True,
        )
        return 1

    vocab_path = Path(args.vocab)
    vocab = json.loads(vocab_path.read_text(encoding="utf-8"))
    log_path = data_dir / "registry_log.jsonl"

    registry = load_registry(registry_path)

    created = 0
    aliased = 0
    already = 0

    concepts = (vocab.get("facets") or {}).get("topic", {}).get("concepts") or []
    for concept in concepts:
        canonical = concept.get("canonical") or ""
        members = concept.get("members") or []
        if not canonical:
            continue

        eid = find_by_surface(registry, "topic", canonical)
        if eid is None:
            eid = create_entry(registry, "topic", canonical, "seed", log_path)
            created += 1
        else:
            already += 1

        for member in members:
            if not member or member == canonical:
                continue
            prev_aliases = list(registry["entries"][eid].get("aliases") or [])
            add_alias(registry, eid, member, "seed", log_path)
            new_aliases = registry["entries"][eid].get("aliases") or []
            if len(new_aliases) > len(prev_aliases):
                aliased += 1

    save_registry(registry_path, registry)
    print(
        f"import_topic_vocabulary: created={created} aliased={aliased} already={already}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
