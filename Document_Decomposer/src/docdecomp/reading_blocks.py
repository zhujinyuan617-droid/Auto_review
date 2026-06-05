from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .io_utils import write_json


SCHEMA_VERSION = "0.1.0"

READING_TYPES = {
    "front_matter",
    "section_heading",
    "paragraph",
    "keywords",
    "list_item",
    "figure",
    "table",
    "formula",
    "caption",
    "footnote",
    "page_header",
    "noise",
    "reference_entry",
    "other",
}

TEXT_BLOCK_TYPES = {"text", "heading_candidate", "caption", "formula", "footnote", "list_item"}
VISUAL_BLOCK_TYPES = {"figure", "table"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def short_text(value: str, max_chars: int) -> str:
    text = normalize_space(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def block_content(block: dict[str, Any]) -> str:
    if block.get("type") in VISUAL_BLOCK_TYPES:
        return str(block.get("caption") or "")
    return str(block.get("text") or block.get("caption") or "")


def join_fragments(parts: list[str]) -> str:
    text = ""
    for raw_part in parts:
        part = normalize_space(raw_part)
        if not part:
            continue
        if not text:
            text = part
        elif re.match(r"^[,.;:)\]\}%]", part):
            text += part
        elif text.endswith(("(", "[", "{", "/", "-")):
            text += part
        else:
            text += " " + part
    return text


def looks_like_page_header(text: str) -> bool:
    value = normalize_space(text)
    return bool(re.fullmatch(r"[A-Z]\.\s+[A-Z][A-Za-z'\-]+ et al\.", value))


def page_header_phrases(content: dict[str, Any]) -> list[str]:
    phrases: set[str] = set()
    for block in content.get("blocks") or []:
        if block.get("type") not in TEXT_BLOCK_TYPES:
            continue
        text = normalize_space(block_content(block))
        if looks_like_page_header(text):
            phrases.add(text)
    return sorted(phrases, key=len, reverse=True)


def clean_embedded_page_headers(text: str, phrases: list[str]) -> tuple[str, list[str]]:
    cleaned = text
    removed: list[str] = []
    for phrase in phrases:
        if phrase not in cleaned:
            continue
        if normalize_space(cleaned) == phrase:
            continue
        cleaned = cleaned.replace(phrase, " ")
        removed.append(phrase)
    return normalize_space(cleaned), removed


def included_paragraph(block: dict[str, Any]) -> bool:
    return block.get("include_in_reading", True) and block.get("reading_type") == "paragraph"


def skippable_interruption(block: dict[str, Any]) -> bool:
    if not block.get("include_in_reading", True):
        return True
    return block.get("reading_type") in {"figure", "table", "caption"}


def incomplete_paragraph(text: str) -> bool:
    value = normalize_space(text)
    if len(value.split()) < 4:
        return False
    if not value:
        return False
    if value[-1] in ".?!;:)]}":
        return False
    if len(value.split()) > 120 and re.search(r"\b[A-Z][a-z]+(?:\s+and\s+[A-Z][a-z]+)?$", value):
        return False
    return True


def strongly_dangling_phrase(text: str) -> bool:
    value = normalize_space(text).lower()
    return value.endswith(
        (
            " due to the",
            " because of the",
            " attributed to the",
            " resulting from the",
            " leading to the",
            " with the",
            " for the",
            " in the",
            " of the",
            " as a",
            " using",
            " include",
            " includes",
            " including",
            " to better characterize gas density distribution and adsorption",
            " gas adsorption capacity",
        )
    )


def starts_like_continuation(text: str) -> bool:
    value = normalize_space(text)
    if not value:
        return False
    if re.match(r"^\[\d+(?:,\d+)*\]\.", value):
        return True
    if re.match(r"^\d{4}[a-z]?\s*[;,)]", value):
        return True
    first = value[0]
    first_word = re.split(r"\s+", value, maxsplit=1)[0].strip(" ,;:()[]{}")
    return first.islower() or first_word.lower() in {
        "and",
        "or",
        "but",
        "which",
        "whereas",
        "thereby",
        "therefore",
        "resulting",
        "leading",
    }


def starts_like_formula_explanation(text: str) -> bool:
    value = normalize_space(text).lower()
    return value.startswith(("where ", "wherein ", "where, ", "here ", "here, "))


def formula_connector_fragment(text: str) -> bool:
    return bool(re.fullmatch(r"(and|or|where|then|therefore)\s*,?", normalize_space(text), flags=re.IGNORECASE))


def looks_like_formula_leadin(text: str) -> bool:
    value = normalize_space(text).lower()
    return value.endswith(":") and bool(
        re.search(r"\b(calculated|defined|expressed|written|given|shown|obtained|computed)\s+as\b", value)
    )


def starts_like_formula_continuation(text: str) -> bool:
    value = normalize_space(text).lower()
    return value.startswith(("represents ", "denotes ", "indicates ", "corresponds ", "is ", "are "))


def eligible_section_kind(section_kind: str | None) -> bool:
    return section_kind not in {"front_matter", "keywords", "references", "acknowledgements", "appendix"}


def renumber_reading_blocks(blocks: list[dict[str, Any]], paper_id: str) -> list[dict[str, Any]]:
    for index, block in enumerate(blocks, start=1):
        block["order"] = index
        block["reading_block_id"] = f"{paper_id}-RB-{index:04d}"
    return blocks


def merge_paragraph_pair(
    target: dict[str, Any],
    continuation: dict[str, Any],
    reason: str,
) -> None:
    target["source_block_ids"] = (target.get("source_block_ids") or []) + (
        continuation.get("source_block_ids") or []
    )
    target["evidence_ids"] = (target.get("evidence_ids") or []) + (continuation.get("evidence_ids") or [])
    pages = [
        page
        for page in [
            target.get("page_start"),
            target.get("page_end"),
            continuation.get("page_start"),
            continuation.get("page_end"),
        ]
        if isinstance(page, int)
    ]
    target["page_start"] = min(pages) if pages else None
    target["page_end"] = max(pages) if pages else None
    target["text"] = join_fragments([target.get("text") or "", continuation.get("text") or ""])

    target_raw = target.get("raw_text") or target.get("text") or ""
    continuation_raw = continuation.get("raw_text") or continuation.get("text") or ""
    if target_raw or continuation_raw:
        target["raw_text"] = join_fragments([target_raw, continuation_raw])

    cleanup = (target.get("cleanup_applied") or []) + (continuation.get("cleanup_applied") or [])
    if cleanup:
        target["cleanup_applied"] = cleanup

    reasons: list[str] = []
    for part in [target.get("join_reason") or "", continuation.get("join_reason") or "", reason]:
        for item in [value.strip() for value in part.split(";")]:
            if item and item not in reasons:
                reasons.append(item)
    target["join_reason"] = "; ".join(reasons)
    target["confidence"] = min(
        _float_or_default(target.get("confidence")),
        _float_or_default(continuation.get("confidence")),
        0.75,
    )


def split_last_source_block(block: dict[str, Any], blocks_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    source_ids = block.get("source_block_ids") or []
    if len(source_ids) < 2:
        return None
    last_id = source_ids[-1]
    source_block = blocks_by_id.get(last_id)
    if not source_block:
        return None
    last_text = block_content(source_block)
    if not last_text:
        return None

    block["source_block_ids"] = source_ids[:-1]
    block["evidence_ids"] = [blocks_by_id[block_id].get("evidence_id") for block_id in source_ids[:-1]]
    pages = [blocks_by_id[block_id].get("page_no") for block_id in source_ids[:-1]]
    pages = [page for page in pages if isinstance(page, int)]
    block["page_start"] = min(pages) if pages else None
    block["page_end"] = max(pages) if pages else None
    block["text"] = join_fragments([block_content(blocks_by_id[block_id]) for block_id in source_ids[:-1]])

    split_block = dict(block)
    split_block["source_block_ids"] = [last_id]
    split_block["evidence_ids"] = [source_block.get("evidence_id")] if source_block.get("evidence_id") else []
    split_block["page_start"] = source_block.get("page_no")
    split_block["page_end"] = source_block.get("page_no")
    split_block["text"] = normalize_space(last_text)
    split_block["caption"] = ""
    split_block["figures"] = []
    split_block["tables"] = []
    split_block["join_reason"] = "auto-split cross-section page-one continuation"
    split_block["confidence"] = min(_float_or_default(block.get("confidence")), 0.65)
    return split_block


def repair_page_one_section_interleaving(
    blocks: list[dict[str, Any]],
    blocks_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    repaired = list(blocks)
    for index, block in enumerate(list(repaired)):
        if not included_paragraph(block):
            continue
        if block.get("section_kind") not in {"abstract"}:
            continue
        if block.get("page_start") != 1:
            continue
        split_block = split_last_source_block(block, blocks_by_id)
        if not split_block:
            continue
        split_text = split_block.get("text") or ""
        if not split_text or not (starts_like_continuation(split_text) or incomplete_paragraph(split_text)):
            block["source_block_ids"] = block.get("source_block_ids", []) + split_block.get("source_block_ids", [])
            block["evidence_ids"] = block.get("evidence_ids", []) + split_block.get("evidence_ids", [])
            block["text"] = join_fragments([block.get("text") or "", split_text])
            continue

        target_index: int | None = None
        for lookahead in range(index + 1, min(len(repaired), index + 12)):
            candidate = repaired[lookahead]
            if not included_paragraph(candidate):
                continue
            if candidate.get("section_kind") != "introduction":
                continue
            if candidate.get("page_start") not in {1, 2}:
                continue
            if not incomplete_paragraph(candidate.get("text") or ""):
                continue
            target_index = lookahead
            break
        if target_index is None:
            block["source_block_ids"] = block.get("source_block_ids", []) + split_block.get("source_block_ids", [])
            block["evidence_ids"] = block.get("evidence_ids", []) + split_block.get("evidence_ids", [])
            block["text"] = join_fragments([block.get("text") or "", split_text])
            continue

        target = repaired[target_index]
        split_block["section_id"] = target.get("section_id")
        split_block["section_title"] = target.get("section_title")
        split_block["section_kind"] = target.get("section_kind")
        split_block["reading_type"] = "paragraph"
        merge_paragraph_pair(target, split_block, "auto-repaired page-one abstract/introduction interleaving")

    return repaired


def coalesce_interrupted_paragraphs(blocks: list[dict[str, Any]], paper_id: str) -> list[dict[str, Any]]:
    removed_indexes: set[int] = set()

    def find_previous_paragraph(index: int, require_incomplete: bool = False) -> int | None:
        skipped = 0
        for lookback in range(index - 1, -1, -1):
            if lookback in removed_indexes:
                continue
            candidate = blocks[lookback]
            if candidate.get("section_id") != blocks[index].get("section_id"):
                break
            if included_paragraph(candidate):
                if starts_like_formula_explanation(candidate.get("text") or "") and starts_like_formula_continuation(
                    blocks[index].get("text") or ""
                ):
                    return lookback
                if starts_like_formula_explanation(candidate.get("text") or ""):
                    skipped += 1
                    if skipped > 8:
                        break
                    continue
                if require_incomplete and not incomplete_paragraph(candidate.get("text") or ""):
                    skipped += 1
                    if skipped > 8:
                        break
                    continue
                return lookback
            if skippable_interruption(candidate):
                skipped += 1
                if skipped > 8:
                    break
                continue
            if starts_like_continuation(blocks[index].get("text") or "") and candidate.get("reading_type") == "section_heading":
                skipped += 1
                if skipped > 8:
                    break
                continue
            break
        return None

    for index, block in enumerate(blocks):
        if index in removed_indexes:
            continue
        if not included_paragraph(block):
            continue
        if not eligible_section_kind(block.get("section_kind")):
            continue
        if not incomplete_paragraph(block.get("text") or ""):
            continue

        skipped = 0
        continuation_index: int | None = None
        for lookahead in range(index + 1, len(blocks)):
            candidate = blocks[lookahead]
            if candidate.get("section_id") != block.get("section_id"):
                break
            if included_paragraph(candidate):
                if strongly_dangling_phrase(block.get("text") or "") and looks_like_formula_leadin(
                    candidate.get("text") or ""
                ):
                    skipped += 1
                    if skipped > 8:
                        break
                    continue
                if starts_like_formula_explanation(candidate.get("text") or ""):
                    if strongly_dangling_phrase(block.get("text") or ""):
                        skipped += 1
                        if skipped > 8:
                            break
                        continue
                elif starts_like_continuation(candidate.get("text") or ""):
                    continuation_index = lookahead
                elif strongly_dangling_phrase(block.get("text") or ""):
                    continuation_index = lookahead
                break
            if skippable_interruption(candidate):
                skipped += 1
                if skipped > 8:
                    break
                continue
            if strongly_dangling_phrase(block.get("text") or "") and candidate.get("reading_type") in {
                "section_heading",
                "formula",
                "table",
                "figure",
                "page_header",
                "noise",
            }:
                skipped += 1
                if skipped > 8:
                    break
                continue
            break

        if continuation_index is None:
            continue

        continuation = blocks[continuation_index]
        merge_paragraph_pair(block, continuation, "auto-merged incomplete paragraph across layout interruption")
        removed_indexes.add(continuation_index)

    for index, block in enumerate(blocks):
        if index in removed_indexes:
            continue
        if not included_paragraph(block):
            continue
        if not eligible_section_kind(block.get("section_kind")):
            continue
        if not starts_like_continuation(block.get("text") or ""):
            continue
        if starts_like_formula_explanation(block.get("text") or ""):
            continue

        previous_index = find_previous_paragraph(index, require_incomplete=True)
        if previous_index is None:
            previous_index = find_previous_paragraph(index, require_incomplete=False)
        if previous_index is None or previous_index in removed_indexes:
            continue

        previous = blocks[previous_index]
        merge_paragraph_pair(previous, block, "auto-merged continuation paragraph across layout interruption")
        removed_indexes.add(index)

    merged = [block for index, block in enumerate(blocks) if index not in removed_indexes]
    return renumber_reading_blocks(merged, paper_id)


def section_map(ai_sections: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    for section in ai_sections.get("sections") or []:
        section_id = section.get("section_id")
        if section_id:
            sections[str(section_id)] = section
    return sections


def block_prompt_item(block: dict[str, Any], max_text_chars: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "block_id": block["block_id"],
        "type": block["type"],
        "page_no": block.get("page_no"),
    }
    if block.get("type") in VISUAL_BLOCK_TYPES:
        item["caption"] = short_text(str(block.get("caption") or ""), max_text_chars)
    else:
        item["text"] = short_text(str(block.get("text") or ""), max_text_chars)
    if block.get("docling_label"):
        item["docling_label"] = block["docling_label"]
    return item


def build_prompt(
    content: dict[str, Any],
    ai_sections: dict[str, Any],
    max_text_chars: int = 650,
) -> list[dict[str, str]]:
    paper_id = content["paper_id"]
    blocks_by_id = {block["block_id"]: block for block in content["blocks"]}
    prompt_sections: list[dict[str, Any]] = []

    for section in ai_sections.get("sections") or []:
        section_block_ids = [block_id for block_id in section.get("block_ids") or [] if block_id in blocks_by_id]
        prompt_sections.append(
            {
                "section_id": section.get("section_id"),
                "title": section.get("title"),
                "section_kind": section.get("section_kind"),
                "page_start": section.get("page_start"),
                "page_end": section.get("page_end"),
                "blocks": [block_prompt_item(blocks_by_id[block_id], max_text_chars) for block_id in section_block_ids],
            }
        )

    user_payload = {
        "paper_id": paper_id,
        "allowed_reading_types": sorted(READING_TYPES),
        "sections": prompt_sections,
    }

    system = (
        "You rebuild academic PDF layout blocks into semantic reading blocks. "
        "The input blocks are Docling layout units, so natural paragraphs may be split by images, tables, "
        "front matter, columns, or false heading candidates. "
        "Use only provided ids. Every source block id must appear exactly once in the output, including "
        "figures, tables, formulas, page headers, noise, and objects with empty captions. "
        "Do not copy source text into the output. Return strict JSON only."
    )
    user = (
        "Group the source blocks into semantic reading blocks for one paper. "
        "A reading block should be one human-readable unit: section heading, paragraph, figure, table, formula, "
        "keyword line, reference entry, page header/noise, or other small unit. "
        "Merge text blocks that belong to the same natural paragraph, including citation fragments and sentence "
        "continuations split by layout. "
        "Do not drop figures, tables, formulas, captions, or low-information page artifacts; classify them as the "
        "best matching reading_type and assign them to the nearest logical position. "
        "Classify repeated short author/title page headers or page artifacts as page_header or noise. "
        "Keep real figures, tables, and formulas as separate reading blocks unless a nearby caption-only block "
        "clearly belongs to the same object. "
        "Every source block id must appear exactly once across all reading_blocks. Do not invent ids. "
        "Use section_id values exactly as provided. Use reading_type only from allowed_reading_types. "
        "Output schema: "
        "{\"paper_id\": string, \"reading_blocks\": [{\"section_id\": string, "
        "\"reading_type\": string, \"source_block_ids\": [string], \"join_reason\": string, "
        "\"confidence\": number}], \"warnings\": [string]}. "
        "The source_block_ids inside one reading block may be non-consecutive only when layout objects interrupted "
        "one natural paragraph. Keep the output in logical reading order. "
        "Here is the input JSON:\n"
        + json.dumps(user_payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_plan(
    plan: dict[str, Any],
    content: dict[str, Any],
    ai_sections: dict[str, Any],
) -> list[str]:
    warnings: list[str] = []
    paper_id = content["paper_id"]
    if plan.get("paper_id") != paper_id:
        warnings.append(f"paper_id mismatch: expected {paper_id}, got {plan.get('paper_id')}")

    reading_blocks = plan.get("reading_blocks")
    if not isinstance(reading_blocks, list):
        return warnings + ["reading_blocks must be a list"]

    allowed_block_ids = {block["block_id"] for block in content["blocks"]}
    sections = section_map(ai_sections)
    block_to_section: dict[str, str] = {}
    for section in ai_sections.get("sections") or []:
        section_id = str(section.get("section_id") or "")
        for block_id in section.get("block_ids") or []:
            block_to_section[str(block_id)] = section_id

    seen: list[str] = []
    for index, reading_block in enumerate(reading_blocks, start=1):
        section_id = reading_block.get("section_id")
        if section_id not in sections:
            warnings.append(f"reading block {index} uses unknown section_id: {section_id}")

        reading_type = reading_block.get("reading_type")
        if reading_type not in READING_TYPES:
            warnings.append(f"reading block {index} uses unknown reading_type: {reading_type}")

        source_block_ids = reading_block.get("source_block_ids")
        if not isinstance(source_block_ids, list) or not source_block_ids:
            warnings.append(f"reading block {index} source_block_ids must be a non-empty list")
            continue

        for block_id in source_block_ids:
            if block_id not in allowed_block_ids:
                warnings.append(f"unknown source_block_id: {block_id}")
            else:
                expected_section = block_to_section.get(block_id)
                if section_id != expected_section:
                    warnings.append(
                        f"block {block_id} assigned to {section_id}, expected section {expected_section}"
                    )
            seen.append(str(block_id))

    seen_set = set(seen)
    missing = sorted(allowed_block_ids - seen_set)
    if missing:
        warnings.append(f"missing source_block_ids count: {len(missing)}")

    unknown = sorted(seen_set - allowed_block_ids)
    if unknown:
        warnings.append(f"unknown source_block_ids count: {len(unknown)}")

    duplicates = sorted(block_id for block_id in seen_set if seen.count(block_id) > 1)
    if duplicates:
        warnings.append(f"duplicate source_block_ids count: {len(duplicates)}")

    return warnings


def repair_plan_coverage(
    plan: dict[str, Any],
    content: dict[str, Any],
    ai_sections: dict[str, Any],
) -> list[str]:
    reading_blocks = plan.get("reading_blocks")
    if not isinstance(reading_blocks, list):
        return []

    blocks = content.get("blocks") or []
    all_ids = [str(block["block_id"]) for block in blocks]
    allowed_ids = set(all_ids)
    warnings: list[str] = []
    cleaned_reading_blocks: list[dict[str, Any]] = []
    for index, reading_block in enumerate(reading_blocks, start=1):
        if not isinstance(reading_block, dict):
            warnings.append(f"dropped non-object reading block at index {index}")
            continue

        source_ids = reading_block.get("source_block_ids")
        if not isinstance(source_ids, list):
            warnings.append(f"dropped reading block {index} with invalid source_block_ids")
            continue

        cleaned_source_ids: list[str] = []
        for raw_block_id in source_ids:
            block_id = str(raw_block_id)
            if block_id not in allowed_ids:
                warnings.append(f"ignored unknown source_block_id in reading block {index}: {block_id}")
                continue
            cleaned_source_ids.append(block_id)

        if not cleaned_source_ids:
            warnings.append(f"dropped reading block {index} after removing unknown source_block_ids")
            continue

        reading_block["source_block_ids"] = cleaned_source_ids
        cleaned_reading_blocks.append(reading_block)

    if len(cleaned_reading_blocks) != len(reading_blocks):
        plan["reading_blocks"] = cleaned_reading_blocks
        reading_blocks = cleaned_reading_blocks

    seen = [
        str(block_id)
        for reading_block in reading_blocks
        if isinstance(reading_block, dict)
        for block_id in (reading_block.get("source_block_ids") or [])
    ]
    missing = [block_id for block_id in all_ids if block_id not in set(seen)]
    if not missing:
        return warnings

    block_to_section: dict[str, str] = {}
    for section in ai_sections.get("sections") or []:
        section_id = str(section.get("section_id") or "")
        for block_id in section.get("block_ids") or []:
            block_to_section[str(block_id)] = section_id

    blocks_by_id = {str(block["block_id"]): block for block in blocks}
    for block_id in missing:
        block = blocks_by_id[block_id]
        block_type = block.get("type")
        reading_type = "other"
        if block_type in READING_TYPES:
            reading_type = str(block_type)
        elif block_type == "heading_candidate":
            reading_type = "section_heading"
        elif block_type == "text":
            reading_type = "paragraph"
        reading_blocks.append(
            {
                "section_id": block_to_section.get(block_id) or nearest_section_id(block_id, ai_sections),
                "reading_type": reading_type,
                "source_block_ids": [block_id],
                "join_reason": "auto-added missing source block after plan coverage validation",
                "confidence": 1.0,
            }
        )
        warnings.append(f"auto-added missing source_block_id: {block_id}")
    return warnings


def nearest_section_id(block_id: str, ai_sections: dict[str, Any]) -> str:
    sections = ai_sections.get("sections") or []
    fallback = ""
    for section in sections:
        section_id = str(section.get("section_id") or "")
        if not fallback:
            fallback = section_id
        block_ids = [str(value) for value in section.get("block_ids") or []]
        if block_id in block_ids:
            return section_id
    return fallback


def _float_or_default(value: Any, default: float = 1.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))


def materialize_reading_blocks(
    plan: dict[str, Any],
    content: dict[str, Any],
    ai_sections: dict[str, Any],
) -> list[dict[str, Any]]:
    paper_id = content["paper_id"]
    blocks_by_id = {block["block_id"]: block for block in content["blocks"]}
    sections = section_map(ai_sections)
    header_phrases = page_header_phrases(content)
    reading_blocks: list[dict[str, Any]] = []

    for index, planned in enumerate(plan.get("reading_blocks") or [], start=1):
        source_ids = [str(block_id) for block_id in planned.get("source_block_ids") or []]
        source_blocks = [blocks_by_id[block_id] for block_id in source_ids if block_id in blocks_by_id]
        if not source_blocks:
            continue
        source_ids = [block["block_id"] for block in source_blocks]
        pages = [block.get("page_no") for block in source_blocks if isinstance(block.get("page_no"), int)]
        section_id = str(planned.get("section_id") or "")
        section = sections.get(section_id, {})
        text_parts = [
            block_content(block)
            for block in source_blocks
            if block.get("type") in TEXT_BLOCK_TYPES and block_content(block)
        ]
        figure_items = [
            {
                "block_id": block["block_id"],
                "evidence_id": block.get("evidence_id"),
                "caption": block.get("caption") or "",
                "image_path": block.get("image_path"),
            }
            for block in source_blocks
            if block.get("type") == "figure"
        ]
        table_items = [
            {
                "block_id": block["block_id"],
                "evidence_id": block.get("evidence_id"),
                "caption": block.get("caption") or "",
                "markdown_path": block.get("markdown_path"),
                "csv_path": block.get("csv_path"),
            }
            for block in source_blocks
            if block.get("type") == "table"
        ]

        visual_captions = [item["caption"] for item in figure_items + table_items if item.get("caption")]
        caption = join_fragments(visual_captions)
        raw_text = join_fragments(text_parts)
        text, removed_headers = clean_embedded_page_headers(raw_text, header_phrases)
        reading_type = planned.get("reading_type")
        if source_blocks and all(looks_like_page_header(block_content(block)) for block in source_blocks):
            reading_type = "page_header"
        if reading_type == "paragraph" and formula_connector_fragment(text):
            reading_type = "formula"

        reading_block: dict[str, Any] = {
            "reading_block_id": f"{paper_id}-RB-{index:04d}",
            "order": index,
            "section_id": section_id,
            "section_title": section.get("title"),
            "section_kind": section.get("section_kind"),
            "reading_type": reading_type,
            "include_in_reading": reading_type not in {"page_header", "noise"},
            "page_start": min(pages) if pages else None,
            "page_end": max(pages) if pages else None,
            "source_block_ids": source_ids,
            "evidence_ids": [block.get("evidence_id") for block in source_blocks if block.get("evidence_id")],
            "text": text,
            "caption": caption,
            "join_reason": str(planned.get("join_reason") or ""),
            "confidence": _float_or_default(planned.get("confidence")),
        }
        if raw_text != text:
            reading_block["raw_text"] = raw_text
        if removed_headers:
            reading_block["cleanup_applied"] = [
                {"type": "embedded_page_header", "text": phrase} for phrase in removed_headers
            ]
        if figure_items:
            reading_block["figures"] = figure_items
        if table_items:
            reading_block["tables"] = table_items
        reading_blocks.append(reading_block)

    reading_blocks = repair_page_one_section_interleaving(reading_blocks, blocks_by_id)
    return coalesce_interrupted_paragraphs(reading_blocks, paper_id)


def build_reading_package(
    plan: dict[str, Any],
    content: dict[str, Any],
    ai_sections: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "paper_id": content["paper_id"],
        "source_files": {
            "content_blocks": "content_blocks.json",
            "ai_sections": "ai_sections.json",
        },
        "reading_blocks": materialize_reading_blocks(plan, content, ai_sections),
        "ai_warnings": plan.get("warnings") or [],
    }


def build_merge_report(
    package: dict[str, Any],
    content: dict[str, Any],
    validation_warnings: list[str],
) -> dict[str, Any]:
    reading_blocks = package.get("reading_blocks") or []
    merged = [block for block in reading_blocks if len(block.get("source_block_ids") or []) > 1]
    excluded = [block for block in reading_blocks if not block.get("include_in_reading", True)]
    return {
        "paper_id": package.get("paper_id"),
        "content_block_count": len(content.get("blocks") or []),
        "reading_block_count": len(reading_blocks),
        "merged_reading_block_count": len(merged),
        "singleton_reading_block_count": len(reading_blocks) - len(merged),
        "excluded_reading_block_count": len(excluded),
        "compression_ratio": round(len(reading_blocks) / max(1, len(content.get("blocks") or [])), 4),
        "validation_warnings": validation_warnings,
        "ai_warnings": package.get("ai_warnings") or [],
        "excluded_examples": [
            {
                "reading_block_id": block.get("reading_block_id"),
                "reading_type": block.get("reading_type"),
                "source_block_ids": block.get("source_block_ids"),
                "text_preview": short_text(block.get("text") or "", 160),
            }
            for block in excluded[:20]
        ],
        "merged_examples": [
            {
                "reading_block_id": block.get("reading_block_id"),
                "section_id": block.get("section_id"),
                "reading_type": block.get("reading_type"),
                "source_block_ids": block.get("source_block_ids"),
                "text_preview": short_text(block.get("text") or block.get("caption") or "", 220),
                "join_reason": block.get("join_reason"),
                "confidence": block.get("confidence"),
            }
            for block in merged[:20]
        ],
    }


def render_reading_md(package: dict[str, Any], paper_dir: Path) -> str:
    lines: list[str] = [f"# {package['paper_id']} Reading Blocks", ""]
    current_section_id: str | None = None

    for block in package.get("reading_blocks") or []:
        if not block.get("include_in_reading", True):
            continue

        section_id = block.get("section_id")
        if section_id != current_section_id:
            current_section_id = section_id
            title = block.get("section_title") or section_id or "Section"
            kind = block.get("section_kind") or "unknown"
            lines.extend([f"## {title}", "", f"<!-- section_id: {section_id}; kind: {kind} -->", ""])

        source_ids = ", ".join(block.get("source_block_ids") or [])
        lines.append(
            f"<!-- {block.get('reading_block_id')} | {block.get('reading_type')} | "
            f"pages {block.get('page_start')}-{block.get('page_end')} | blocks: {source_ids} -->"
        )

        text = block.get("text") or ""
        if text:
            lines.extend([text, ""])

        for figure in block.get("figures") or []:
            image_path = figure.get("image_path")
            caption = figure.get("caption") or figure.get("evidence_id") or "figure"
            if image_path:
                lines.extend([f"![{caption}]({image_path})", ""])
            if caption:
                lines.extend([f"*{caption}*", ""])

        for table in block.get("tables") or []:
            caption = table.get("caption") or table.get("evidence_id") or "table"
            if caption:
                lines.extend([f"**{caption}**", ""])
            markdown_path = table.get("markdown_path")
            if markdown_path:
                full_path = paper_dir / markdown_path
                if full_path.exists():
                    lines.extend([full_path.read_text(encoding="utf-8").strip(), ""])
                else:
                    lines.extend([f"[table markdown]({markdown_path})", ""])

    return "\n".join(lines).rstrip() + "\n"
