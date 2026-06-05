from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.io_utils import atomic_write_csv_dicts
from docdecomp.reading_blocks import (
    incomplete_paragraph,
    looks_like_page_header,
    normalize_space,
    starts_like_formula_explanation,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated semantic reading blocks.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--paper-id", action="append", help="Validate one paper id. May be repeated.")
    parser.add_argument("--report", default=str(ROOT / "reports" / "reading_blocks_quality.csv"))
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def first_words(text: str, count: int = 20) -> str:
    words = normalize_space(text).split()
    return " ".join(words[:count])


def continuation_like(text: str) -> bool:
    value = normalize_space(text)
    if not value:
        return False
    if re.match(r"^a\s+b\s+s\s+t\s+r\s+a\s+c\s+t\b", value, flags=re.IGNORECASE):
        return False
    if starts_like_formula_explanation(value) or value.lower().startswith("where:"):
        return False
    if re.search(r"\b(calculated|defined|expressed|written|given)\s+as$", value, flags=re.IGNORECASE):
        return False
    if re.search(r"\b(calculated|defined|expressed|written|given)\b.+:$", value, flags=re.IGNORECASE):
        return False
    first = value[0]
    first_word = re.split(r"\s+", value, maxsplit=1)[0].strip(" ,;:()[]{}").lower()
    if first_word == "while":
        return False
    return first.islower() or first_word in {
        "and",
        "or",
        "but",
        "which",
        "where",
        "whereas",
        "thereby",
        "therefore",
        "resulting",
        "leading",
        "occupied",
        "respectively",
    }


def looks_like_metadata_line(text: str) -> bool:
    value = normalize_space(text)
    return bool(
        re.search(r"\bReceived\b.+\bAccepted\b", value)
        or re.search(r"\bAvailable online\b", value)
    )


def looks_like_symbol_list(block: dict[str, Any]) -> bool:
    text = normalize_space(block.get("text") or "")
    title = normalize_space(block.get("section_title") or "").lower()
    if "symbol" in title:
        return True
    if block.get("section_kind") == "front_matter" and len(re.findall(r"\b[A-Za-z][A-Za-z0-9,/+-]*\s*,", text)) >= 4:
        return True
    return False


def mirrors_incomplete_source(block: dict[str, Any], source_by_id: dict[str, dict[str, Any]]) -> bool:
    source_ids = block.get("source_block_ids") or []
    if len(source_ids) != 1:
        return False
    source = source_by_id.get(str(source_ids[0]))
    if not source:
        return False
    source_text = normalize_space(source.get("text") or source.get("caption") or "")
    block_text = normalize_space(block.get("text") or block.get("caption") or "")
    return bool(source_text and block_text == source_text and incomplete_paragraph(source_text))


def validate_paper(paper_dir: Path) -> dict[str, Any]:
    paper_id = paper_dir.name
    content = load_json(paper_dir / "content_blocks.json")
    reading = load_json(paper_dir / "reading_blocks.json")
    blocks = content.get("blocks") or []
    source_by_id = {str(block["block_id"]): block for block in blocks}
    reading_blocks = reading.get("reading_blocks") or []

    all_ids = [block["block_id"] for block in blocks]
    referenced = [
        block_id
        for reading_block in reading_blocks
        for block_id in (reading_block.get("source_block_ids") or [])
    ]
    unique_refs = set(referenced)
    missing = sorted(set(all_ids) - unique_refs)
    unknown = sorted(unique_refs - set(all_ids))
    duplicate_count = sum(max(0, referenced.count(block_id) - 1) for block_id in unique_refs)

    included_blocks = [block for block in reading_blocks if block.get("include_in_reading", True)]
    excluded_blocks = [block for block in reading_blocks if not block.get("include_in_reading", True)]
    merged_blocks = [block for block in reading_blocks if len(block.get("source_block_ids") or []) > 1]

    embedded_page_headers = [
        block
        for block in included_blocks
        if looks_like_page_header(normalize_space(block.get("text") or ""))
    ]
    raw_header_cleanup = [
        block for block in included_blocks if block.get("cleanup_applied")
    ]
    incomplete: list[dict[str, Any]] = []
    for index, block in enumerate(included_blocks):
        if block.get("reading_type") != "paragraph" or not incomplete_paragraph(block.get("text") or ""):
            continue
        if block.get("section_kind") in {"front_matter", "keywords"}:
            continue
        if mirrors_incomplete_source(block, source_by_id):
            continue
        if looks_like_metadata_line(block.get("text") or "") or looks_like_symbol_list(block):
            continue
        next_included = included_blocks[index + 1] if index + 1 < len(included_blocks) else None
        if next_included and next_included.get("section_id") == block.get("section_id"):
            if next_included.get("reading_type") == "formula":
                continue
            if next_included.get("reading_type") in {"figure", "table"}:
                text = normalize_space(block.get("text") or "")
                if re.search(r"\b(Fig|Table|Equation|Eq)\.?\s*\d", text, flags=re.IGNORECASE):
                    continue
        incomplete.append(block)
    continuation_starts = [
        block
        for block in included_blocks
        if block.get("reading_type") == "paragraph" and continuation_like(block.get("text") or "")
    ]
    empty_visuals = [
        block
        for block in included_blocks
        if block.get("reading_type") in {"figure", "table"} and not block.get("caption") and not block.get("text")
    ]

    return {
        "paper_id": paper_id,
        "content_blocks": len(all_ids),
        "reading_blocks": len(reading_blocks),
        "referenced_blocks": len(referenced),
        "unique_referenced_blocks": len(unique_refs),
        "missing_count": len(missing),
        "unknown_count": len(unknown),
        "duplicate_count": duplicate_count,
        "merged_count": len(merged_blocks),
        "excluded_count": len(excluded_blocks),
        "embedded_page_header_count": len(embedded_page_headers),
        "cleanup_count": len(raw_header_cleanup),
        "incomplete_paragraph_count": len(incomplete),
        "continuation_start_count": len(continuation_starts),
        "empty_visual_count": len(empty_visuals),
        "missing_examples": "; ".join(missing[:5]),
        "incomplete_examples": " | ".join(
            f"{block.get('reading_block_id')}: {first_words(block.get('text') or '')}"
            for block in incomplete[:3]
        ),
        "continuation_start_examples": " | ".join(
            f"{block.get('reading_block_id')}: {first_words(block.get('text') or '')}"
            for block in continuation_starts[:3]
        ),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    library_dir = Path(args.library_dir)
    paper_dirs = [library_dir / paper_id for paper_id in args.paper_id] if args.paper_id else sorted(
        path for path in library_dir.iterdir() if path.is_dir() and (path / "reading_blocks.json").exists()
    )
    rows = [validate_paper(path) for path in paper_dirs]

    report_path = Path(args.report)
    atomic_write_csv_dicts(report_path, list(rows[0].keys()) if rows else [], rows)

    print(f"Wrote {report_path}")
    for row in rows:
        print(
            f"{row['paper_id']}: {row['content_blocks']} content -> {row['reading_blocks']} reading; "
            f"missing={row['missing_count']}, dup={row['duplicate_count']}, "
            f"incomplete={row['incomplete_paragraph_count']}, continuation_start={row['continuation_start_count']}, "
            f"excluded={row['excluded_count']}"
        )
        if row["incomplete_examples"]:
            print(f"  incomplete examples: {row['incomplete_examples']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
