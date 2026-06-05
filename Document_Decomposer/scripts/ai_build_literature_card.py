from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config, run_ai_cli
from docdecomp.ai_cache import build_ai_fingerprint, cache_hit, meta_path_for, write_ai_cache_meta
from docdecomp.literature_card import (
    build_prompt,
    build_repair_prompt,
    ensure_card_defaults,
    fallback_literature_card,
    load_json,
    validate_card,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use AI to extract a literature card from reading blocks.")
    parser.add_argument("--paper-id", default="S01", help="Library paper id, for example S01.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--config", default=None, help="Path to ai.local.json. Defaults to config/ai.local.json.")
    parser.add_argument("--output-name", default="literature_card.json")
    parser.add_argument("--dry-run", action="store_true", help="Write prompt preview instead of calling AI.")
    parser.add_argument("--from-card", action="store_true", help="Normalize and validate an existing card without calling AI.")
    parser.add_argument("--force", action="store_true", help="Ignore AI cache and call the model.")
    parser.add_argument("--max-block-chars", type=int, default=900, help="Max chars per reading block sent to AI.")
    parser.add_argument("--max-ai-attempts", type=int, default=2, help="AI attempts before writing a failed candidate.")
    parser.add_argument("--save-failed-attempts", action="store_true", help="Write failed AI candidates for prompt debugging.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paper_dir = Path(args.library_dir) / args.paper_id
    reading_path = paper_dir / "reading_blocks.json"
    metadata_path = paper_dir / "metadata_candidates.json"
    reading = load_json(reading_path)
    metadata = load_json(metadata_path)

    output_path = paper_dir / args.output_name
    if args.from_card:
        card = load_json(output_path)
        card = ensure_card_defaults(card, reading, metadata)
        validation = validate_card(card, reading)
        if validation["status"] != "ok":
            card.setdefault("ai_warnings", []).append(f"validator:{validation['warnings']}")
        write_json(output_path, card)
        print(f"Normalized {output_path}")
        print(
            f"Validation: {validation['status']}; evidence={validation['evidence_count']}; "
            f"unknown_rb={validation['unknown_reading_block_count']}; "
            f"bad_source={validation['bad_source_ref_count']}; "
            f"missing_evidence={validation['missing_evidence_count']}; "
            f"page_mismatch={validation['page_mismatch_count']}; "
            f"empty_text={validation['empty_required_text_count']}"
        )
        return 0

    messages = build_prompt(reading, metadata, args.max_block_chars)

    if args.dry_run:
        preview_path = paper_dir / "literature_card.prompt.json"
        write_json(preview_path, {"messages": messages})
        print(f"Prompt preview: {preview_path}")
        return 0

    config_path = Path(args.config) if args.config else None
    config = load_ai_config(ROOT, config_path)
    schema_hint = (
        "Return only one JSON object with keys: schema_version, paper_id, paper, classification, "
        "fuzzy_keywords, core_question, study_design, variables, mechanisms, key_findings, "
        "quantitative_results, limitations, review_section_hints, ai_warnings. Do not wrap the JSON in Markdown."
    )
    fingerprint = build_ai_fingerprint(
        stage="literature_card",
        paper_id=reading["paper_id"],
        messages=messages,
        schema_hint=schema_hint,
        config=config,
        input_paths={
            "reading_blocks": reading_path,
            "metadata_candidates": metadata_path,
        },
        parameters={
            "max_block_chars": args.max_block_chars,
            "max_ai_attempts": args.max_ai_attempts,
            "output_name": args.output_name,
        },
    )
    meta_path = meta_path_for(output_path)
    if not args.force and cache_hit(meta_path=meta_path, required_outputs=[output_path], fingerprint=fingerprint):
        print(f"Cache hit: {output_path}")
        return 0

    client = OpenAICompatibleClient(config)
    attempts = max(1, args.max_ai_attempts)
    card = {}
    validation = {}
    current_messages = messages
    for attempt in range(1, attempts + 1):
        card = client.chat_json(current_messages, schema_hint)
        card = ensure_card_defaults(card, reading, metadata)
        validation = validate_card(card, reading)
        if validation["status"] == "ok":
            write_json(output_path, card)
            write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[output_path])
            print(f"Wrote {output_path}")
            break
        if args.save_failed_attempts:
            debug_path = output_path.with_suffix(f".attempt{attempt}.failed.json")
            write_json(debug_path, {"candidate": card, "validation": validation})
            print(f"Wrote failed attempt {debug_path}")
        if attempt < attempts:
            print(f"Attempt {attempt} failed validation; retrying with validator feedback.")
            current_messages = build_repair_prompt(messages, card, validation)
    else:
        fallback = fallback_literature_card(reading, metadata)
        fallback_validation = validate_card(fallback, reading)
        if fallback_validation["status"] == "ok":
            card = fallback
            validation = fallback_validation
            write_json(output_path, card)
            write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[output_path])
            print(f"Wrote fallback {output_path}")
        else:
            card.setdefault("ai_warnings", []).append(f"validator:{validation['warnings']}")
            card.setdefault("ai_warnings", []).append(f"fallback_validator:{fallback_validation['warnings']}")
            failed_path = output_path.with_suffix(".failed.json")
            write_json(failed_path, card)
            print(f"Wrote failed candidate {failed_path}")
            fallback_path = output_path.with_suffix(".fallback.failed.json")
            write_json(fallback_path, fallback)
            print(f"Wrote failed fallback {fallback_path}")
            validation = fallback_validation
    print(
        f"Validation: {validation['status']}; evidence={validation['evidence_count']}; "
        f"unknown_rb={validation['unknown_reading_block_count']}; "
        f"bad_source={validation['bad_source_ref_count']}; "
        f"missing_evidence={validation['missing_evidence_count']}; "
        f"page_mismatch={validation['page_mismatch_count']}; "
        f"empty_text={validation['empty_required_text_count']}"
    )
    if validation["warnings"]:
        print(f"Warnings: {validation['warnings']}")
    return 0 if validation["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(run_ai_cli(main))
