from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .. import engine_bridge

engine_bridge.ensure_engine_scripts_on_path()  # adds Document_Decomposer/scripts to sys.path

import ai_organize_sections as sections_stage  # engine script (now importable)  # noqa: E402
from docdecomp.io_utils import atomic_write_text, write_json  # noqa: E402
from docdecomp.reading_blocks import (  # noqa: E402
    build_merge_report,
    build_prompt as build_reading_prompt,
    build_reading_package,
    load_json,
    render_reading_md,
    repair_plan_coverage,
    validate_plan,
)
from docdecomp.slim_card import (  # noqa: E402
    SLIM_SCHEMA_HINT,
    build_slim_prompt,
    ensure_slim_defaults,
    validate_slim_card,
)

# Match the engine scripts' schema hints (incl. the "no Markdown" instruction) so
# a real client behaves the same as the engine's own runs.
SECTIONS_HINT = (
    "Return only one JSON object with keys: paper_id, sections, warnings. "
    "Do not wrap the JSON in Markdown."
)
READING_HINT = (
    "Return only one JSON object with keys: paper_id, reading_blocks, warnings. "
    "Do not wrap the JSON in Markdown."
)


class AIClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]], response_schema_hint: str) -> dict[str, Any]:
        ...


def run_sections_stage(paper_dir: Path, client: AIClient) -> dict[str, Any]:
    content, metadata = sections_stage.load_package(paper_dir)
    messages = sections_stage.build_prompt(content, metadata, 900)
    result = client.chat_json(messages, SECTIONS_HINT)
    allowed = {b["block_id"] for b in content.get("blocks", [])}
    warnings = sections_stage.validate_ai_sections(result, content.get("paper_id", ""), allowed)
    if warnings:
        # Mirror the engine: preserve any warnings the model emitted, then append ours.
        result.setdefault("validation_warnings", []).extend(warnings)
    write_json(paper_dir / "ai_sections.json", result)
    return result


def run_reading_stage(paper_dir: Path, client: AIClient) -> dict[str, Any]:
    content = load_json(paper_dir / "content_blocks.json")
    ai_sections = load_json(paper_dir / "ai_sections.json")
    messages = build_reading_prompt(content, ai_sections, 650)
    plan = client.chat_json(messages, READING_HINT)
    warnings = [*repair_plan_coverage(plan, content, ai_sections), *validate_plan(plan, content, ai_sections)]
    if warnings:
        # Mirror the engine: persist repair/validation notes back into the plan file.
        plan.setdefault("validation_warnings", []).extend(warnings)
    package = build_reading_package(plan, content, ai_sections)
    report = build_merge_report(package, content, warnings)
    write_json(paper_dir / "reading_blocks.plan.json", plan)
    write_json(paper_dir / "reading_blocks.json", package)
    write_json(paper_dir / "merge_report.json", report)
    atomic_write_text(paper_dir / "reading.md", render_reading_md(package, paper_dir), encoding="utf-8")
    return package


def _front_matter_page1(paper_dir: Path, max_blocks: int = 30) -> str:
    """首页版面原文(作者署名/机构所在),喂给卡片 AI 顺手抽 authors_raw。"""
    try:
        doc = load_json(paper_dir / "content_blocks.json")
    except (OSError, ValueError):
        return ""
    out: list[str] = []
    for b in doc.get("blocks") or []:
        if str(b.get("page_no")) == "1" and b.get("text"):
            out.append(str(b["text"]))
        if len(out) >= max_blocks:
            break
    return "\n".join(out)[:6000]


def run_card_stage(paper_dir: Path, client: AIClient) -> dict[str, Any]:
    reading = load_json(paper_dir / "reading_blocks.json")
    metadata = load_json(paper_dir / "metadata_candidates.json")
    messages = build_slim_prompt(reading, metadata, 900,
                                 front_matter=_front_matter_page1(paper_dir))
    raw = client.chat_json(messages, SLIM_SCHEMA_HINT)
    card = ensure_slim_defaults(raw, reading, metadata)
    # Don't pollute the card schema with a "validation" key (the engine never does).
    # If the card is incomplete, surface it the way the engine's --from-card path does.
    validation = validate_slim_card(card)
    if validation.get("status") != "ok":
        card.setdefault("ai_warnings", []).append(f"validator:{validation.get('warnings')}")
    write_json(paper_dir / "literature_card.json", card)
    return card


def run_ai_pipeline(paper_dir: Path, client: AIClient) -> dict[str, Any]:
    run_sections_stage(paper_dir, client)
    run_reading_stage(paper_dir, client)
    return run_card_stage(paper_dir, client)
