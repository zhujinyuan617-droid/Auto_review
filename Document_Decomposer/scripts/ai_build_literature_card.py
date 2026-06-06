"""Build a SLIM index card (architecture v2) from reading blocks.

Card = metadata + coarse tags + a fixed-format coarse summary (non-fact, for linking
only). No quotes, no claims-with-numbers. See docdecomp/slim_card.py and CONNECTION_PLAN.md.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config
from docdecomp.ai_cache import build_ai_fingerprint, cache_hit, meta_path_for, write_ai_cache_meta
from docdecomp.literature_card import load_json, write_json
from docdecomp.slim_card import (
    SLIM_SCHEMA_HINT,
    build_slim_prompt,
    build_slim_repair_prompt,
    ensure_slim_defaults,
    fallback_slim_card,
    validate_slim_card,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Use AI to extract a slim index card from reading blocks.")
    p.add_argument("--paper-id", default="S01")
    p.add_argument("--library-dir", default=str(ROOT / "library"))
    p.add_argument("--config", default=None, help="Path to ai.local.json. Defaults to config/ai.local.json.")
    p.add_argument("--output-name", default="literature_card.json")
    p.add_argument("--dry-run", action="store_true", help="Write prompt preview instead of calling AI.")
    p.add_argument("--from-card", action="store_true", help="Normalize/validate an existing card without calling AI.")
    p.add_argument("--force", action="store_true", help="Ignore AI cache and call the model.")
    p.add_argument("--max-block-chars", type=int, default=900)
    p.add_argument("--max-ai-attempts", type=int, default=2)
    p.add_argument("--save-failed-attempts", action="store_true")
    return p.parse_args()


def _print_validation(v: dict) -> None:
    print(f"Validation: {v['status']}; tags={v['n_tags']}; findings={v['n_findings']}; warnings={v['warnings']}")


def main() -> int:
    args = parse_args()
    paper_dir = Path(args.library_dir) / args.paper_id
    reading = load_json(paper_dir / "reading_blocks.json")
    metadata = load_json(paper_dir / "metadata_candidates.json")
    output_path = paper_dir / args.output_name

    if args.from_card:
        card = ensure_slim_defaults(load_json(output_path), reading, metadata)
        v = validate_slim_card(card)
        if v["status"] != "ok":
            card.setdefault("ai_warnings", []).append(f"validator:{v['warnings']}")
        write_json(output_path, card)
        print(f"Normalized {output_path}")
        _print_validation(v)
        return 0

    messages = build_slim_prompt(reading, metadata, args.max_block_chars)
    if args.dry_run:
        write_json(paper_dir / "literature_card.prompt.json", {"messages": messages})
        print(f"Prompt preview: {paper_dir / 'literature_card.prompt.json'}")
        return 0

    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    fingerprint = build_ai_fingerprint(
        stage="slim_card", paper_id=reading["paper_id"], messages=messages,
        schema_hint=SLIM_SCHEMA_HINT, config=config,
        input_paths={"reading_blocks": paper_dir / "reading_blocks.json",
                     "metadata_candidates": paper_dir / "metadata_candidates.json"},
        parameters={"max_block_chars": args.max_block_chars, "schema": "slim-0.2.0",
                    "output_name": args.output_name},
    )
    meta_path = meta_path_for(output_path)
    if not args.force and cache_hit(meta_path=meta_path, required_outputs=[output_path], fingerprint=fingerprint):
        print(f"Cache hit: {output_path}")
        return 0

    client = OpenAICompatibleClient(config)
    attempts = max(1, args.max_ai_attempts)
    current = messages
    card, v = {}, {}
    for attempt in range(1, attempts + 1):
        card = ensure_slim_defaults(client.chat_json(current, SLIM_SCHEMA_HINT), reading, metadata)
        v = validate_slim_card(card)
        if v["status"] == "ok":
            write_json(output_path, card)
            write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[output_path])
            print(f"Wrote {output_path}")
            _print_validation(v)
            return 0
        if args.save_failed_attempts:
            write_json(output_path.with_suffix(f".attempt{attempt}.failed.json"), {"candidate": card, "validation": v})
        if attempt < attempts:
            print(f"Attempt {attempt} failed ({v['warnings']}); retrying with feedback.")
            current = build_slim_repair_prompt(messages, card, v)

    fb = fallback_slim_card(reading, metadata)
    fb_v = validate_slim_card(fb)
    if fb_v["status"] == "ok":
        write_json(output_path, fb)
        write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[output_path])
        print(f"Wrote fallback {output_path}")
        _print_validation(fb_v)
        return 0
    card.setdefault("ai_warnings", []).append(f"validator:{v['warnings']}")
    write_json(output_path.with_suffix(".failed.json"), card)
    print(f"Wrote failed candidate {output_path.with_suffix('.failed.json')}")
    _print_validation(v)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
