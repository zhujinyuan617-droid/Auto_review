"""Bulk-resolve card domain_tags to registry topic entries (library-wide).

Scans every literature_card.json for domain_tags, runs exact/alias lookup against
the element registry, calls the AI client once for any unresolved batch (if
--config is given), creates new entries for remaining unresolved tags, and writes
classification.topic_ids back to each card.

No --config → client=None → every unresolved tag becomes a new entry (no AI call).
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
from docdecomp.card_tags import resolve_topics_bulk  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--library-dir",
        default=str(ROOT / "library"),
        help="Root library directory (default: ROOT/library)",
    )
    ap.add_argument(
        "--data-dir",
        default=str(ROOT / "data" / "elements"),
        help="Directory containing registry.json and registry_log.jsonl "
             "(default: ROOT/data/elements)",
    )
    ap.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to ai.local.json; if omitted no AI call is made and every "
             "unresolved tag creates a new entry",
    )
    args = ap.parse_args()

    library_dir = Path(args.library_dir)
    data_dir = Path(args.data_dir)
    registry_path = data_dir / "registry.json"
    log_path = data_dir / "registry_log.jsonl"

    if not registry_path.exists():
        print(
            f"[error] registry.json not found at {registry_path}. "
            "Run bootstrap_element_registry.py first.",
            file=sys.stderr,
            flush=True,
        )
        return 1

    client = None
    if args.config is not None:
        config_path = Path(args.config)
        client = OpenAICompatibleClient(load_ai_config(ROOT, config_path))

    stats = resolve_topics_bulk(library_dir, registry_path, log_path, client)
    print(
        f"resolve_topics_bulk: "
        f"tags_total={stats['tags_total']} "
        f"resolved_exact={stats['resolved_exact']} "
        f"resolved_ai={stats['resolved_ai']} "
        f"created={stats['created']} "
        f"cards_updated={stats['cards_updated']} "
        f"ai_calls={stats['ai_calls']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
