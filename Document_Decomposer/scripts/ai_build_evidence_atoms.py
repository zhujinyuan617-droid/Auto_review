from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_cache import build_ai_fingerprint, cache_hit, meta_path_for, write_ai_cache_meta
from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config
from docdecomp.evidence_synthesis import (
    build_evidence_atoms_prompt,
    build_evidence_atoms_repair_prompt,
    ensure_evidence_atoms_defaults,
    fallback_evidence_atoms,
    load_json,
    validate_evidence_atoms,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use AI to extract article-internal hard evidence atoms.")
    parser.add_argument("--paper-id", default="S01", help="Library paper id, for example S01.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--config", default=None, help="Path to ai.local.json. Defaults to config/ai.local.json.")
    parser.add_argument("--reading-name", default="reading_blocks.json")
    parser.add_argument("--output-name", default="evidence_atoms.json")
    parser.add_argument("--dry-run", action="store_true", help="Write prompt preview instead of calling AI.")
    parser.add_argument("--from-atoms", action="store_true", help="Normalize and validate an existing atom file without calling AI.")
    parser.add_argument("--force", action="store_true", help="Ignore AI cache and call the model.")
    parser.add_argument("--max-block-chars", type=int, default=900, help="Max chars per reading block sent to AI.")
    parser.add_argument("--max-ai-attempts", type=int, default=3, help="AI attempts before using fallback.")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    paper_dir = Path(args.library_dir) / args.paper_id
    reading_path = paper_dir / args.reading_name
    output_path = paper_dir / args.output_name
    reading = load_json(reading_path)

    if args.from_atoms:
        package = load_json(output_path)
        package = ensure_evidence_atoms_defaults(package, reading)
        validation = validate_evidence_atoms(package, reading)
        if validation["status"] != "ok":
            package.setdefault("ai_warnings", []).append(f"validator:{validation['warnings']}")
        write_json(output_path, package)
        print(f"Normalized {output_path}")
        print(
            f"Validation: {validation['status']}; atoms={validation['atom_count']}; "
            f"unknown_rb={validation['unknown_reading_block_count']}; "
            f"bad_source={validation['bad_source_ref_count']}; "
            f"page_mismatch={validation['page_mismatch_count']}; "
            f"quote_not_found={validation['quote_not_found_count']}"
        )
        return 0 if validation["status"] == "ok" else 1

    messages = build_evidence_atoms_prompt(reading, args.max_block_chars)

    if args.dry_run:
        preview_path = paper_dir / "evidence_atoms.prompt.json"
        write_json(preview_path, {"messages": messages})
        print(f"Prompt preview: {preview_path}")
        return 0

    config_path = Path(args.config) if args.config else None
    config = load_ai_config(ROOT, config_path)
    schema_hint = (
        "Return only one JSON object with keys: schema_version, paper_id, source_files, "
        "evidence_atoms, ai_warnings. Do not wrap the JSON in Markdown."
    )
    fingerprint = build_ai_fingerprint(
        stage="evidence_atoms",
        paper_id=reading["paper_id"],
        messages=messages,
        schema_hint=schema_hint,
        config=config,
        input_paths={"reading_blocks": reading_path},
        parameters={
            "max_block_chars": args.max_block_chars,
            "max_ai_attempts": args.max_ai_attempts,
            "reading_name": args.reading_name,
            "output_name": args.output_name,
        },
    )
    meta_path = meta_path_for(output_path)
    if not args.force and cache_hit(meta_path=meta_path, required_outputs=[output_path], fingerprint=fingerprint):
        print(f"Cache hit: {output_path}")
        return 0

    client = OpenAICompatibleClient(config)
    attempts = max(1, args.max_ai_attempts)
    package: dict = {}
    validation: dict = {}
    current_messages = messages
    for attempt in range(1, attempts + 1):
        package = client.chat_json(current_messages, schema_hint)
        package = ensure_evidence_atoms_defaults(package, reading)
        validation = validate_evidence_atoms(package, reading)
        if validation["status"] == "ok":
            write_json(output_path, package)
            write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[output_path])
            print(f"Wrote {output_path}")
            break
        if attempt < attempts:
            print(f"Attempt {attempt} failed validation; retrying with validator feedback.")
            current_messages = build_evidence_atoms_repair_prompt(messages, package, validation)
    else:
        fallback = fallback_evidence_atoms(reading)
        fallback_validation = validate_evidence_atoms(fallback, reading)
        if fallback_validation["status"] == "ok":
            package = fallback
            validation = fallback_validation
            write_json(output_path, package)
            write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[output_path])
            print(f"Wrote fallback {output_path}")
        else:
            package.setdefault("ai_warnings", []).append(f"validator:{validation.get('warnings', '')}")
            package.setdefault("ai_warnings", []).append(f"fallback_validator:{fallback_validation['warnings']}")
            failed_path = output_path.with_suffix(".failed.json")
            write_json(failed_path, package)
            validation = fallback_validation
            print(f"Wrote failed candidate {failed_path}")

    print(
        f"Validation: {validation['status']}; atoms={validation['atom_count']}; "
        f"unknown_rb={validation['unknown_reading_block_count']}; "
        f"bad_source={validation['bad_source_ref_count']}; "
        f"page_mismatch={validation['page_mismatch_count']}; "
        f"quote_not_found={validation['quote_not_found_count']}; "
        f"empty_text={validation['empty_required_text_count']}"
    )
    if validation["warnings"]:
        print(f"Warnings: {validation['warnings']}")
    return 0 if validation["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
