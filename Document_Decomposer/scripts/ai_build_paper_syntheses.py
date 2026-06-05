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
    build_paper_syntheses_prompt,
    build_paper_syntheses_repair_prompt,
    canonicalize_paper_syntheses_with_baseline,
    ensure_paper_syntheses_defaults,
    fallback_paper_syntheses,
    load_json,
    validate_syntheses_against_baseline,
    validate_paper_syntheses,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use AI to build article-internal syntheses from evidence atoms.")
    parser.add_argument("--paper-id", default="S01", help="Library paper id, for example S01.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--config", default=None, help="Path to ai.local.json. Defaults to config/ai.local.json.")
    parser.add_argument("--atoms-name", default="evidence_atoms.json")
    parser.add_argument("--output-name", default="paper_syntheses.json")
    parser.add_argument("--baseline", default=None, help="Optional manual synthesis baseline JSON for coverage validation.")
    parser.add_argument("--dry-run", action="store_true", help="Write prompt preview instead of calling AI.")
    parser.add_argument("--from-syntheses", action="store_true", help="Normalize and validate an existing syntheses file without calling AI.")
    parser.add_argument("--force", action="store_true", help="Ignore AI cache and call the model.")
    parser.add_argument("--max-atom-chars", type=int, default=650, help="Max chars per evidence atom sent to AI.")
    parser.add_argument("--max-ai-attempts", type=int, default=3, help="AI attempts before using fallback.")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    paper_dir = Path(args.library_dir) / args.paper_id
    atoms_path = paper_dir / args.atoms_name
    output_path = paper_dir / args.output_name
    evidence_atoms = load_json(atoms_path)
    baseline_requirements = None
    baseline_path = Path(args.baseline) if args.baseline else None
    if baseline_path:
        baseline = load_json(baseline_path)
        baseline_requirements = (baseline.get("papers") or {}).get(args.paper_id)

    if args.from_syntheses:
        package = load_json(output_path)
        package = ensure_paper_syntheses_defaults(package, evidence_atoms)
        validation = validate_paper_syntheses(package, evidence_atoms)
        baseline_validation = validate_syntheses_against_baseline(package, baseline_requirements)
        if baseline_validation["missing_baseline_theme_count"]:
            validation["status"] = "fail"
            validation["warnings"] = "; ".join(
                part for part in [
                    validation.get("warnings", ""),
                    "missing_baseline:" + ",".join(baseline_validation["missing_baseline_themes"]),
                ]
                if part
            )
        if validation["status"] != "ok":
            package.setdefault("ai_warnings", []).append(f"validator:{validation['warnings']}")
        write_json(output_path, package)
        print(f"Normalized {output_path}")
        print(
            f"Validation: {validation['status']}; syntheses={validation['synthesis_count']}; "
            f"unknown_atom={validation['unknown_evidence_atom_count']}; "
            f"weak_support={validation['weak_support_count']}; "
            f"duplicate_support={validation['duplicate_support_count']}; "
            f"unsupported_scope={validation['unsupported_scope_value_count']}"
        )
        return 0 if validation["status"] == "ok" else 1

    messages = build_paper_syntheses_prompt(evidence_atoms, args.max_atom_chars, baseline_requirements)

    if args.dry_run:
        preview_path = paper_dir / "paper_syntheses.prompt.json"
        write_json(preview_path, {"messages": messages})
        print(f"Prompt preview: {preview_path}")
        return 0

    config_path = Path(args.config) if args.config else None
    config = load_ai_config(ROOT, config_path)
    schema_hint = (
        "Return only one JSON object with keys: schema_version, paper_id, source_files, "
        "paper_syntheses, ai_warnings. Do not wrap the JSON in Markdown."
    )
    fingerprint = build_ai_fingerprint(
        stage="paper_syntheses",
        paper_id=evidence_atoms["paper_id"],
        messages=messages,
        schema_hint=schema_hint,
        config=config,
        input_paths={"evidence_atoms": atoms_path},
        parameters={
            "max_atom_chars": args.max_atom_chars,
            "max_ai_attempts": args.max_ai_attempts,
            "atoms_name": args.atoms_name,
            "output_name": args.output_name,
            "baseline": str(baseline_path) if baseline_path else "",
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
        package = ensure_paper_syntheses_defaults(package, evidence_atoms)
        validation = validate_paper_syntheses(package, evidence_atoms)
        baseline_validation = validate_syntheses_against_baseline(package, baseline_requirements)
        if baseline_validation["missing_baseline_theme_count"]:
            validation["status"] = "fail"
            validation["warnings"] = "; ".join(
                part for part in [
                    validation.get("warnings", ""),
                    "missing_baseline:" + ",".join(baseline_validation["missing_baseline_themes"]),
                ]
                if part
            )
            validation["baseline"] = baseline_validation
        if validation["status"] == "ok":
            package = canonicalize_paper_syntheses_with_baseline(package, evidence_atoms, baseline_requirements)
            validation = validate_paper_syntheses(package, evidence_atoms)
            baseline_validation = validate_syntheses_against_baseline(package, baseline_requirements)
            if baseline_validation["missing_baseline_theme_count"]:
                validation["status"] = "fail"
                validation["warnings"] = "; ".join(
                    part for part in [
                        validation.get("warnings", ""),
                        "missing_baseline:" + ",".join(baseline_validation["missing_baseline_themes"]),
                    ]
                    if part
                )
                if attempt < attempts:
                    print(f"Attempt {attempt} failed baseline canonicalization; retrying with validator feedback.")
                    current_messages = build_paper_syntheses_repair_prompt(messages, package, validation)
                    continue
            write_json(output_path, package)
            write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[output_path])
            print(f"Wrote {output_path}")
            break
        if attempt < attempts:
            print(f"Attempt {attempt} failed validation; retrying with validator feedback.")
            current_messages = build_paper_syntheses_repair_prompt(messages, package, validation)
    else:
        fallback = fallback_paper_syntheses(evidence_atoms)
        fallback_validation = validate_paper_syntheses(fallback, evidence_atoms)
        fallback_baseline_validation = validate_syntheses_against_baseline(fallback, baseline_requirements)
        if fallback_baseline_validation["missing_baseline_theme_count"]:
            fallback_validation["status"] = "fail"
            fallback_validation["warnings"] = "; ".join(
                part for part in [
                    fallback_validation.get("warnings", ""),
                    "missing_baseline:" + ",".join(fallback_baseline_validation["missing_baseline_themes"]),
                ]
                if part
            )
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
        f"Validation: {validation['status']}; syntheses={validation['synthesis_count']}; "
        f"unknown_atom={validation['unknown_evidence_atom_count']}; "
        f"weak_support={validation['weak_support_count']}; "
        f"duplicate_support={validation['duplicate_support_count']}; "
        f"unsupported_scope={validation['unsupported_scope_value_count']}; "
        f"empty_text={validation['empty_required_text_count']}"
    )
    if validation["warnings"]:
        print(f"Warnings: {validation['warnings']}")
    return 0 if validation["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
