from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config, run_ai_cli
from docdecomp.ai_cache import build_ai_fingerprint, cache_hit, meta_path_for, write_ai_cache_meta
from docdecomp.io_utils import atomic_write_text
from docdecomp.reading_blocks import (
    build_merge_report,
    build_prompt,
    build_reading_package,
    load_json,
    repair_plan_coverage,
    render_reading_md,
    validate_plan,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use AI to rebuild Docling layout blocks into semantic reading blocks.")
    parser.add_argument("--paper-id", default="S01", help="Library paper id, for example S01.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--config", default=None, help="Path to ai.local.json. Defaults to config/ai.local.json.")
    parser.add_argument("--sections-name", default="ai_sections.json")
    parser.add_argument("--plan-name", default="reading_blocks.plan.json")
    parser.add_argument("--output-name", default="reading_blocks.json")
    parser.add_argument("--md-name", default="reading.md")
    parser.add_argument("--report-name", default="merge_report.json")
    parser.add_argument("--dry-run", action="store_true", help="Write prompt preview instead of calling AI.")
    parser.add_argument("--from-plan", action="store_true", help="Rebuild outputs from an existing plan without calling AI.")
    parser.add_argument("--force", action="store_true", help="Ignore AI cache and call the model.")
    parser.add_argument("--max-text-chars", type=int, default=650, help="Max text chars per block sent to AI.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paper_dir = Path(args.library_dir) / args.paper_id
    content_path = paper_dir / "content_blocks.json"
    sections_path = paper_dir / args.sections_name
    content = load_json(content_path)
    ai_sections = load_json(sections_path)
    plan_path = paper_dir / args.plan_name
    output_path = paper_dir / args.output_name
    md_path = paper_dir / args.md_name
    report_path = paper_dir / args.report_name

    if args.from_plan:
        plan = load_json(plan_path)
        repair_warnings = repair_plan_coverage(plan, content, ai_sections)
        validation_warnings = validate_plan(plan, content, ai_sections)
        validation_warnings = [*repair_warnings, *validation_warnings]
        package = build_reading_package(plan, content, ai_sections)
        report = build_merge_report(package, content, validation_warnings)
        write_json(output_path, package)
        write_json(report_path, report)
        atomic_write_text(md_path, render_reading_md(package, paper_dir), encoding="utf-8")
        print(f"Rebuilt {output_path} from {plan_path}")
        print(f"Wrote {md_path}")
        print(f"Wrote {report_path}")
        return 0

    messages = build_prompt(content, ai_sections, args.max_text_chars)

    if args.dry_run:
        preview_path = paper_dir / "reading_blocks.prompt.json"
        write_json(preview_path, {"messages": messages})
        print(f"Prompt preview: {preview_path}")
        return 0

    config_path = Path(args.config) if args.config else None
    config = load_ai_config(ROOT, config_path)
    schema_hint = (
        "Return only one JSON object with keys: paper_id, reading_blocks, warnings. "
        "Do not wrap the JSON in Markdown."
    )
    fingerprint = build_ai_fingerprint(
        stage="reading_blocks_plan",
        paper_id=content["paper_id"],
        messages=messages,
        schema_hint=schema_hint,
        config=config,
        input_paths={
            "content_blocks": content_path,
            "ai_sections": sections_path,
        },
        parameters={
            "max_text_chars": args.max_text_chars,
            "sections_name": args.sections_name,
            "plan_name": args.plan_name,
        },
    )
    meta_path = meta_path_for(plan_path)
    if not args.force and cache_hit(
        meta_path=meta_path,
        required_outputs=[plan_path, output_path, md_path, report_path],
        fingerprint=fingerprint,
    ):
        print(f"Cache hit: {plan_path}")
        return 0
    if not args.force and cache_hit(meta_path=meta_path, required_outputs=[plan_path], fingerprint=fingerprint):
        plan = load_json(plan_path)
        repair_warnings = repair_plan_coverage(plan, content, ai_sections)
        validation_warnings = validate_plan(plan, content, ai_sections)
        validation_warnings = [*repair_warnings, *validation_warnings]
        package = build_reading_package(plan, content, ai_sections)
        report = build_merge_report(package, content, validation_warnings)
        write_json(output_path, package)
        write_json(report_path, report)
        atomic_write_text(md_path, render_reading_md(package, paper_dir), encoding="utf-8")
        write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[plan_path, output_path, md_path, report_path])
        print(f"Cache hit: {plan_path}")
        print(f"Rebuilt derived reading outputs from cached plan")
        return 0

    client = OpenAICompatibleClient(config)
    plan = client.chat_json(messages, schema_hint)

    repair_warnings = repair_plan_coverage(plan, content, ai_sections)
    validation_warnings = validate_plan(plan, content, ai_sections)
    validation_warnings = [*repair_warnings, *validation_warnings]
    if validation_warnings:
        plan.setdefault("validation_warnings", []).extend(validation_warnings)

    package = build_reading_package(plan, content, ai_sections)
    report = build_merge_report(package, content, validation_warnings)

    write_json(plan_path, plan)
    write_json(output_path, package)
    write_json(report_path, report)
    atomic_write_text(md_path, render_reading_md(package, paper_dir), encoding="utf-8")
    write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[plan_path, output_path, md_path, report_path])

    print(f"Wrote {plan_path}")
    print(f"Wrote {output_path}")
    print(f"Wrote {md_path}")
    print(f"Wrote {report_path}")
    if validation_warnings:
        print("Validation warnings:")
        for warning in validation_warnings:
            print(f"- {warning}")
    else:
        print("Validation warnings: none")
    print(
        "Blocks: "
        f"{report['content_block_count']} content -> {report['reading_block_count']} reading "
        f"({report['merged_reading_block_count']} merged)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_ai_cli(main))
