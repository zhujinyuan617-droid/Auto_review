from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config
from docdecomp.ai_cache import build_ai_fingerprint, cache_hit, meta_path_for, write_ai_cache_meta
from docdecomp.io_utils import write_json


SECTION_KINDS = [
    "front_matter",
    "abstract",
    "keywords",
    "introduction",
    "methods",
    "results",
    "discussion",
    "results_discussion",
    "conclusion",
    "acknowledgements",
    "references",
    "appendix",
    "other",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Use an AI model to organize content blocks into paper sections.")
    parser.add_argument("--paper-id", default="S01", help="Library paper id, for example S01.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--config", default=None, help="Path to ai.local.json. Defaults to config/ai.local.json.")
    parser.add_argument("--output-name", default="ai_sections.json")
    parser.add_argument("--dry-run", action="store_true", help="Write prompt preview instead of calling AI.")
    parser.add_argument("--force", action="store_true", help="Ignore AI cache and call the model.")
    parser.add_argument("--max-text-chars", type=int, default=900, help="Max text chars per block sent to AI.")
    return parser.parse_args()


def load_package(paper_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    content = json.loads((paper_dir / "content_blocks.json").read_text(encoding="utf-8"))
    metadata = json.loads((paper_dir / "metadata_candidates.json").read_text(encoding="utf-8"))
    return content, metadata


def block_for_prompt(block: dict[str, Any], max_text_chars: int) -> dict[str, Any]:
    out = {
        "block_id": block["block_id"],
        "type": block["type"],
        "page_no": block.get("page_no"),
        "evidence_id": block["evidence_id"],
    }
    if "docling_label" in block:
        out["docling_label"] = block["docling_label"]
    if block["type"] in {"figure", "table"}:
        out["caption"] = (block.get("caption") or "")[:max_text_chars]
    else:
        out["text"] = (block.get("text") or "")[:max_text_chars]
    return out


def build_prompt(content: dict[str, Any], metadata: dict[str, Any], max_text_chars: int) -> list[dict[str, str]]:
    paper_id = content["paper_id"]
    blocks = [block_for_prompt(block, max_text_chars) for block in content["blocks"]]
    user_payload = {
        "paper_id": paper_id,
        "metadata_candidates": metadata.get("metadata_candidates", {}),
        "allowed_section_kinds": SECTION_KINDS,
        "blocks": blocks,
    }
    system = (
        "You organize academic paper content blocks into logical sections. "
        "Use only the provided block_id values. Do not invent block ids. "
        "Every input block_id must appear exactly once in the output, including figures, tables, "
        "formulas, footnotes, page artifacts, and objects with empty captions. "
        "Docling heading_candidate blocks are only candidates: decide whether they are true section headings. "
        "PDF layout order may interleave front matter, abstract, and introduction on page 1. "
        "Use semantic cues as well as nearby headings: abstract text usually summarizes the whole paper, while "
        "introduction text discusses background, prior work, objectives, and references in detail. "
        "Do not copy full block text into the output. Return strict JSON only."
    )
    user = (
        "Group these content blocks into sections for one academic paper. "
        "Preserve reading order. Merge false heading candidates back into the appropriate section. "
        "Do not drop any block just because it has no text or empty caption; assign it to the nearest logical section. "
        "If a block appears after an Abstract heading but semantically reads as Introduction background or prior-work "
        "discussion, assign it to the Introduction section. "
        "Each section must include a title, section_kind, page_start, page_end, and block_ids. "
        f"Use section_id values in this exact pattern: {paper_id}-AISEC-001, {paper_id}-AISEC-002, ... "
        "Use section_kind only from allowed_section_kinds. "
        "Output schema: "
        "{\"paper_id\": string, \"sections\": [{\"section_id\": string, \"order\": number, "
        "\"title\": string, \"section_kind\": string, \"page_start\": number|null, "
        "\"page_end\": number|null, \"block_ids\": [string], \"notes\": string}], "
        "\"warnings\": [string]}. "
        "Here is the input JSON:\n"
        + json.dumps(user_payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_ai_sections(result: dict[str, Any], paper_id: str, allowed_block_ids: set[str]) -> list[str]:
    warnings: list[str] = []
    if result.get("paper_id") != paper_id:
        warnings.append(f"paper_id mismatch: expected {paper_id}, got {result.get('paper_id')}")
    sections = result.get("sections")
    if not isinstance(sections, list):
        warnings.append("sections must be a list")
        return warnings
    seen: set[str] = set()
    for index, section in enumerate(sections, start=1):
        block_ids = section.get("block_ids")
        if not isinstance(block_ids, list):
            warnings.append(f"section {index} block_ids is not a list")
            continue
        for block_id in block_ids:
            if block_id not in allowed_block_ids:
                warnings.append(f"unknown block_id: {block_id}")
            if block_id in seen:
                warnings.append(f"duplicate block_id: {block_id}")
            seen.add(block_id)
        if section.get("section_kind") not in SECTION_KINDS:
            warnings.append(f"unknown section_kind: {section.get('section_kind')}")
    missing = sorted(allowed_block_ids - seen)
    if missing:
        warnings.append(f"missing block_ids count: {len(missing)}")
    return warnings


def main() -> int:
    args = parse_args()
    paper_dir = Path(args.library_dir) / args.paper_id
    content_path = paper_dir / "content_blocks.json"
    metadata_path = paper_dir / "metadata_candidates.json"
    content, metadata = load_package(paper_dir)
    messages = build_prompt(content, metadata, args.max_text_chars)
    output_path = paper_dir / args.output_name

    if args.dry_run:
        preview_path = paper_dir / "ai_sections.prompt.json"
        write_json(preview_path, {"messages": messages})
        print(f"Prompt preview: {preview_path}")
        return 0

    config_path = Path(args.config) if args.config else None
    config = load_ai_config(ROOT, config_path)
    schema_hint = (
        "Return only one JSON object with keys: paper_id, sections, warnings. "
        "Do not wrap the JSON in Markdown."
    )
    fingerprint = build_ai_fingerprint(
        stage="ai_sections",
        paper_id=content["paper_id"],
        messages=messages,
        schema_hint=schema_hint,
        config=config,
        input_paths={
            "content_blocks": content_path,
            "metadata_candidates": metadata_path,
        },
        parameters={
            "max_text_chars": args.max_text_chars,
            "output_name": args.output_name,
        },
    )
    meta_path = meta_path_for(output_path)
    if not args.force and cache_hit(meta_path=meta_path, required_outputs=[output_path], fingerprint=fingerprint):
        print(f"Cache hit: {output_path}")
        return 0

    client = OpenAICompatibleClient(config)
    result = client.chat_json(messages, schema_hint)

    allowed_block_ids = {block["block_id"] for block in content["blocks"]}
    validation_warnings = validate_ai_sections(result, content["paper_id"], allowed_block_ids)
    if validation_warnings:
        result.setdefault("validation_warnings", []).extend(validation_warnings)

    write_json(output_path, result)
    write_ai_cache_meta(meta_path=meta_path, fingerprint=fingerprint, outputs=[output_path])
    print(f"Wrote {output_path}")
    if validation_warnings:
        print("Validation warnings:")
        for warning in validation_warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
