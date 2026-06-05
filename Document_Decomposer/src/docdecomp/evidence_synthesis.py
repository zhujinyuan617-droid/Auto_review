from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .io_utils import atomic_write_csv_dicts, write_json


SCHEMA_VERSION = "0.1.0"

ATOM_TYPES = {
    "method",
    "variable",
    "mechanism",
    "result",
    "quantitative_result",
    "limitation",
    "scope",
    "background",
    "other",
}

SYNTHESIS_TYPES = {
    "method_result_link",
    "mechanism_result_link",
    "variable_effect",
    "limitation_scope",
    "evidence_summary",
    "other",
}

CONFIDENCE_VALUES = {"high", "medium", "low"}
SKIP_SECTION_KINDS = {"references", "acknowledgements", "appendix"}
SKIP_READING_TYPES = {"page_header", "noise", "reference_entry"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_space(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def short_text(value: Any, max_chars: int) -> str:
    text = normalize_space(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def block_text(block: dict[str, Any]) -> str:
    return str(block.get("text") or block.get("caption") or "")


def reading_block_map(reading: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(block.get("reading_block_id")): block for block in reading.get("reading_blocks") or []}


def source_to_reading_block_map(reading: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for block in reading.get("reading_blocks") or []:
        for source_id in block.get("source_block_ids") or []:
            mapping[str(source_id)] = block
    return mapping


def reading_block_prompt_item(block: dict[str, Any], max_block_chars: int) -> dict[str, Any]:
    return {
        "reading_block_id": block.get("reading_block_id"),
        "section_title": block.get("section_title"),
        "section_kind": block.get("section_kind"),
        "reading_type": block.get("reading_type"),
        "page_start": block.get("page_start"),
        "page_end": block.get("page_end"),
        "source_block_ids": block.get("source_block_ids") or [],
        "text": short_text(block_text(block), max_block_chars),
    }


def evidence_atom_prompt_item(atom: dict[str, Any], max_atom_chars: int) -> dict[str, Any]:
    return {
        "evidence_atom_id": atom.get("evidence_atom_id"),
        "atom_type": atom.get("atom_type"),
        "minimal_claim": short_text(atom.get("minimal_claim") or "", max_atom_chars),
        "quote": short_text(atom.get("quote") or "", max_atom_chars),
        "reading_block_id": atom.get("reading_block_id"),
        "page_start": atom.get("page_start"),
        "page_end": atom.get("page_end"),
        "topic_tags": atom.get("topic_tags") or [],
        "confidence": atom.get("confidence"),
    }


def baseline_prompt_item(theme: dict[str, Any]) -> dict[str, Any]:
    return {
        "theme_id": theme.get("theme_id"),
        "label": theme.get("label"),
        "expected_atom_ids": theme.get("expected_atom_ids") or [],
        "min_support_overlap": theme.get("min_support_overlap") or 1,
        "term_groups": theme.get("term_groups") or [],
    }


def relevant_reading_blocks_for_atoms(reading: dict[str, Any], limit: int = 150) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, block in enumerate(reading.get("reading_blocks") or []):
        if not block.get("include_in_reading", True):
            continue
        if block.get("section_kind") in SKIP_SECTION_KINDS:
            continue
        if block.get("reading_type") in SKIP_READING_TYPES:
            continue
        text = normalize_space(block_text(block))
        if len(text) < 25:
            continue

        section_kind = str(block.get("section_kind") or "")
        reading_type = str(block.get("reading_type") or "")
        lowered = text.lower()
        score = 0
        score += {
            "abstract": 160,
            "conclusion": 145,
            "results_discussion": 135,
            "results": 130,
            "discussion": 120,
            "methods": 105,
            "keywords": 35,
            "front_matter": 25,
            "introduction": 20,
        }.get(section_kind, 10)
        if reading_type in {"paragraph", "list_item"}:
            score += 25
        if reading_type in {"figure", "table", "caption"}:
            score += 35
        if reading_type == "section_heading":
            score -= 80
        if re.search(r"\d", text):
            score += 15
        if any(
            token in lowered
            for token in [
                "this study",
                "this paper",
                "in this work",
                "employed",
                "used",
                "method",
                "experiment",
                "simulation",
                "model",
                "pressure",
                "temperature",
                "mpa",
                "adsorption",
                "diffusion",
                "tortuosity",
                "methane",
                "carbon dioxide",
                "ch4",
                "co2",
                "result",
                "suggest",
                "indicate",
                "increase",
                "decrease",
                "higher",
                "lower",
                "greater",
                "conclude",
                "limitation",
            ]
        ):
            score += 45
        scored.append((score, -index, block))

    selected = [block for _, _, block in sorted(scored, reverse=True)[:limit]]
    return sorted(selected, key=lambda block: int(block.get("order") or 0))


def build_evidence_atoms_prompt(
    reading: dict[str, Any],
    max_block_chars: int = 900,
) -> list[dict[str, str]]:
    paper_id = reading["paper_id"]
    blocks = [
        reading_block_prompt_item(block, max_block_chars)
        for block in relevant_reading_blocks_for_atoms(reading)
    ]
    payload = {
        "paper_id": paper_id,
        "allowed_atom_types": sorted(ATOM_TYPES),
        "allowed_confidence": sorted(CONFIDENCE_VALUES),
        "reading_blocks": blocks,
    }
    system = (
        "You extract hard evidence atoms from academic-paper reading blocks. "
        "Use only the supplied reading blocks and ids. Do not invent facts. "
        "Each evidence atom must cite exactly one reading block, and quote must be a short exact excerpt from that block. "
        "The atom is not a synthesis: keep minimal_claim close to the quote."
    )
    user = (
        "Build evidence_atoms JSON for this one paper. Prefer 8 to 24 strong atoms when supported. "
        "Each atom should capture one hard evidence unit: a method, variable/condition, mechanism, result, "
        "quantitative result, limitation, scope boundary, or important background statement. "
        "Do not combine distant evidence at this stage. Do not cite references-section entries. "
        "quote must be copied from the cited reading block and should usually be one sentence or sentence fragment. "
        "minimal_claim should be a conservative near-quote paraphrase, not a broad conclusion. "
        "source_block_ids must be copied from the cited reading block and must be a subset of that block's ids. "
        "page_start and page_end must exactly match the cited reading block. "
        "Return only one JSON object with keys schema_version, paper_id, source_files, evidence_atoms, ai_warnings. "
        "Each evidence_atoms item must have exactly these keys: evidence_atom_id, atom_type, quote, minimal_claim, "
        "reading_block_id, source_block_ids, page_start, page_end, topic_tags, confidence. "
        "Use evidence_atom_id values like S01-EVATOM-0001. If the evidence is weak or unsupported, omit it. "
        "Do not wrap the JSON in Markdown. Input JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_evidence_atoms_repair_prompt(
    previous_messages: list[dict[str, str]],
    candidate: dict[str, Any],
    validation: dict[str, Any],
) -> list[dict[str, str]]:
    repair_instruction = (
        "The previous evidence_atoms JSON failed validation. Return a corrected complete evidence_atoms JSON object. "
        "Regenerate from the original supplied reading blocks. Do not explain and do not use Markdown. "
        "Every quote must be copied from the cited reading block exactly after whitespace normalization. "
        "Drop unsupported atoms instead of inventing ids or evidence. Validation summary:\n"
        + json.dumps(validation, ensure_ascii=False)
    )
    if candidate.get("evidence_atoms"):
        return [
            *previous_messages,
            {"role": "assistant", "content": json.dumps(candidate, ensure_ascii=False)},
            {"role": "user", "content": repair_instruction},
        ]
    return [*previous_messages, {"role": "user", "content": repair_instruction}]


def build_paper_syntheses_prompt(
    evidence_atoms: dict[str, Any],
    max_atom_chars: int = 650,
    baseline_requirements: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    paper_id = evidence_atoms["paper_id"]
    atoms = [
        evidence_atom_prompt_item(atom, max_atom_chars)
        for atom in evidence_atoms.get("evidence_atoms") or []
    ]
    payload = {
        "paper_id": paper_id,
        "allowed_synthesis_types": sorted(SYNTHESIS_TYPES),
        "allowed_confidence": sorted(CONFIDENCE_VALUES),
        "evidence_atoms": atoms,
    }
    if baseline_requirements:
        payload["manual_baseline_themes"] = [
            baseline_prompt_item(theme)
            for theme in baseline_requirements.get("themes") or []
            if isinstance(theme, dict)
        ]
    system = (
        "You build article-internal syntheses from evidence atoms. "
        "Use only the supplied evidence_atom_id values. Do not use outside knowledge or reading blocks directly. "
        "A synthesis claim must combine two or more atoms into a larger within-paper conclusion."
    )
    user = (
        "Build paper_syntheses JSON for this one paper as a stable, deterministic article-level synthesis map. "
        "Return exactly 5 syntheses when at least 5 independent article-internal themes are supported; otherwise "
        "return one synthesis per supported independent theme. Do not return more than 5 syntheses. "
        "Use this stable priority order when the evidence supports these theme families: "
        "1) study setup/method plus direct characterization result; "
        "2) key variable/condition effects on outcomes; "
        "3) mechanism-to-result explanation; "
        "4) explicit ranking/comparison evidence, including mineral/material/gas/model orders, highest/lowest, "
        "best/worst, greater/lower, and A > B > C relationships; "
        "5) model/fitting/quantitative comparison; "
        "6) limitation, scope, or future-work boundary. "
        "Always preserve a supported explicit ranking/comparison synthesis when the atoms contain order, >, highest, "
        "lowest, best fit, greater than, lower than, or pressure-dependent ranking language. Do not let a broad "
        "temperature/pressure effect synthesis replace a mineral/material/gas ranking synthesis. "
        "If a paper has several closely related sub-results under one theme family, combine them into one synthesis "
        "rather than splitting them across multiple syntheses. "
        "If manual_baseline_themes are supplied in the input JSON, treat them as required coverage targets derived "
        "from a manual reading of the evidence atoms. Cover every supplied theme_id exactly once when the listed "
        "expected_atom_ids exist in the input. The synthesis for that theme must cite at least min_support_overlap "
        "of its expected_atom_ids and should use wording that matches the theme label and term_groups. "
        "Each synthesis must list at least two supporting_evidence_atom_ids. "
        "Use the smallest sufficient support set for the theme, normally 2 to 6 atoms. Prefer high-confidence atoms, "
        "direct result/mechanism/limitation atoms, and the earliest method/scope atom needed to bound the claim. "
        "Sort supporting_evidence_atom_ids in ascending evidence_atom_id order. "
        "The claim can be more inferential than an evidence atom, but it must be fully supported by the listed atoms. "
        "reasoning should explain how the atoms combine. scope should state only the boundary supported by the "
        "listed atoms. If scope uses exact temperatures, pressures, sample counts, or other numbers, those exact "
        "numbers must appear in the selected atoms' quote or minimal_claim text. "
        "limitations should list stated or obvious scope limits from the selected atoms; use an empty array if none are supported. "
        "Do not mention reading_block_id in the synthesis object; the evidence layer already stores that. "
        "Use stable concise wording: do not add optional background, citations, or extra examples when they are not "
        "needed for the selected theme. Do not create duplicate syntheses that cover the same theme with different words. "
        "Return only one JSON object with keys schema_version, paper_id, source_files, paper_syntheses, ai_warnings. "
        "Each paper_syntheses item must have exactly these keys: synthesis_id, synthesis_type, claim, "
        "supporting_evidence_atom_ids, reasoning, scope, confidence, limitations. "
        "Use synthesis_id values like S01-SYN-0001. Do not wrap the JSON in Markdown. Input JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_paper_syntheses_repair_prompt(
    previous_messages: list[dict[str, str]],
    candidate: dict[str, Any],
    validation: dict[str, Any],
) -> list[dict[str, str]]:
    repair_instruction = (
        "The previous paper_syntheses JSON failed validation. Return a corrected complete paper_syntheses JSON object. "
        "Regenerate from the original supplied evidence atoms. Do not explain and do not use Markdown. "
        "Every synthesis must cite at least two known evidence_atom_id values. "
        "If validation reports missing_baseline themes, add or revise syntheses so every supplied manual_baseline_theme "
        "is covered by at least min_support_overlap expected_atom_ids and matching theme wording. "
        "Drop unsupported syntheses instead of inventing ids. Validation summary:\n"
        + json.dumps(validation, ensure_ascii=False)
    )
    if candidate.get("paper_syntheses"):
        return [
            *previous_messages,
            {"role": "assistant", "content": json.dumps(candidate, ensure_ascii=False)},
            {"role": "user", "content": repair_instruction},
        ]
    return [*previous_messages, {"role": "user", "content": repair_instruction}]


def normalize_confidence(value: Any, default: str = "medium") -> str:
    confidence = str(value or "").strip().lower()
    return confidence if confidence in CONFIDENCE_VALUES else default


def normalize_atom_type(value: Any) -> str:
    atom_type = str(value or "").strip().lower()
    return atom_type if atom_type in ATOM_TYPES else "other"


def normalize_synthesis_type(value: Any) -> str:
    synthesis_type = str(value or "").strip().lower()
    return synthesis_type if synthesis_type in SYNTHESIS_TYPES else "other"


def normalize_string_list(value: Any, limit: int | None = None) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for raw in value:
        text = normalize_space(raw)
        if text and text not in items:
            items.append(text)
        if limit is not None and len(items) >= limit:
            break
    return items


def quote_in_block(quote: str, block: dict[str, Any]) -> bool:
    quote_text = normalize_space(quote)
    if not quote_text:
        return False
    return quote_text in normalize_space(block_text(block))


def infer_topic_tags(text: str, limit: int = 8) -> list[str]:
    lowered = text.lower()
    tags: list[str] = []
    candidates = [
        "kerogen",
        "shale",
        "methane",
        "ch4",
        "carbon dioxide",
        "co2",
        "adsorption",
        "diffusion",
        "tortuosity",
        "pressure",
        "temperature",
        "langmuir",
        "freundlich",
        "henry",
        "illite",
        "montmorillonite",
        "calcite",
        "mineral",
        "pore",
        "gcmc",
        "molecular dynamics",
        "experiment",
        "simulation",
    ]
    for candidate in candidates:
        if candidate in lowered:
            tags.append(candidate)
        if len(tags) >= limit:
            break
    return tags or ["paper-evidence"]


def normalize_evidence_atom(atom: dict[str, Any], reading: dict[str, Any]) -> dict[str, Any]:
    blocks_by_id = reading_block_map(reading)
    blocks_by_source = source_to_reading_block_map(reading)
    reading_block_id = str(
        atom.get("reading_block_id")
        or atom.get("block_id")
        or atom.get("source_reading_block_id")
        or ""
    )
    source_ids = [str(value) for value in (atom.get("source_block_ids") or atom.get("source_ids") or [])]
    block = blocks_by_id.get(reading_block_id)
    if block is None and source_ids:
        block = blocks_by_source.get(source_ids[0])
        if block:
            reading_block_id = str(block.get("reading_block_id") or "")

    if block:
        allowed_source_ids = [str(value) for value in (block.get("source_block_ids") or [])]
        source_set = set(allowed_source_ids)
        source_ids = [source_id for source_id in source_ids if source_id in source_set] or allowed_source_ids
        page_start = block.get("page_start")
        page_end = block.get("page_end")
    else:
        page_start = atom.get("page_start")
        page_end = atom.get("page_end")

    quote = normalize_space(atom.get("quote") or atom.get("text") or "")
    if not quote and block:
        quote = evidence_quote(block, max_chars=280)

    minimal_claim = normalize_space(atom.get("minimal_claim") or atom.get("claim") or quote)
    topic_tags = normalize_string_list(atom.get("topic_tags") or atom.get("tags"), limit=10)
    if not topic_tags:
        topic_tags = infer_topic_tags(" ".join([quote, minimal_claim]))

    return {
        "evidence_atom_id": str(atom.get("evidence_atom_id") or ""),
        "atom_type": normalize_atom_type(atom.get("atom_type") or atom.get("type")),
        "quote": quote,
        "minimal_claim": minimal_claim,
        "reading_block_id": reading_block_id,
        "source_block_ids": source_ids,
        "page_start": page_start,
        "page_end": page_end,
        "topic_tags": topic_tags,
        "confidence": normalize_confidence(atom.get("confidence")),
    }


def renumber_evidence_atoms(package: dict[str, Any], paper_id: str) -> dict[str, Any]:
    for index, atom in enumerate(package.get("evidence_atoms") or [], start=1):
        atom["evidence_atom_id"] = f"{paper_id}-EVATOM-{index:04d}"
    return package


def ensure_evidence_atoms_defaults(package: dict[str, Any], reading: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(package, dict):
        package = {}
    paper_id = str(reading.get("paper_id") or package.get("paper_id") or "")
    atoms_value = package.get("evidence_atoms")
    if not isinstance(atoms_value, list):
        atoms_value = package.get("atoms") if isinstance(package.get("atoms"), list) else []

    atoms: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw_atom in atoms_value:
        if not isinstance(raw_atom, dict):
            continue
        atom = normalize_evidence_atom(raw_atom, reading)
        key = (atom.get("reading_block_id") or "", normalize_space(atom.get("quote") or "").lower())
        if key in seen:
            continue
        seen.add(key)
        atoms.append(atom)

    normalized = {
        "schema_version": package.get("schema_version") or SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_files": package.get("source_files") if isinstance(package.get("source_files"), dict) else {
            "reading_blocks": "reading_blocks.json",
        },
        "evidence_atoms": atoms,
        "ai_warnings": normalize_string_list(package.get("ai_warnings")),
    }
    normalized["source_files"].setdefault("reading_blocks", "reading_blocks.json")
    return renumber_evidence_atoms(normalized, paper_id)


def sentence_split(text: str) -> list[str]:
    value = normalize_space(text)
    if not value:
        return []
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9(])", value)
    if len(sentences) == 1 and len(value) > 450:
        sentences = re.split(r";\s+", value)
    return [sentence.strip() for sentence in sentences if len(sentence.split()) >= 5]


def sentence_score(sentence: str, section_kind: str) -> int:
    lowered = sentence.lower()
    score = 0
    if section_kind in {"abstract", "conclusion"}:
        score += 40
    if section_kind in {"methods", "results", "discussion", "results_discussion"}:
        score += 30
    if re.search(r"\d", sentence):
        score += 15
    keyword_weights = {
        "this study": 35,
        "this paper": 30,
        "in this work": 30,
        "employed": 25,
        "used": 15,
        "method": 15,
        "experiment": 20,
        "simulation": 20,
        "model": 15,
        "pressure": 20,
        "temperature": 20,
        "mpa": 20,
        "adsorption": 25,
        "diffusion": 25,
        "tortuosity": 25,
        "methane": 15,
        "carbon dioxide": 15,
        "ch4": 15,
        "co2": 15,
        "result": 25,
        "suggest": 25,
        "found": 20,
        "increase": 20,
        "decrease": 20,
        "higher": 15,
        "lower": 15,
        "greater": 15,
        "conclude": 25,
        "limitation": 30,
        "future": 15,
    }
    for keyword, weight in keyword_weights.items():
        if keyword in lowered:
            score += weight
    return score


def infer_atom_type(sentence: str, block: dict[str, Any]) -> str:
    lowered = sentence.lower()
    section_kind = str(block.get("section_kind") or "")
    if any(token in lowered for token in ["limitation", "future work", "uncertainty", "not representative"]):
        return "limitation"
    if any(token in lowered for token in ["pressure", "temperature", "mpa", "range", "ratio"]):
        if any(token in lowered for token in ["result", "increase", "decrease", "greater", "higher", "lower"]):
            return "quantitative_result" if re.search(r"\d", sentence) else "result"
        return "variable"
    if section_kind == "methods" or any(token in lowered for token in ["method", "employed", "used", "experiment", "simulation", "model"]):
        return "method"
    if any(token in lowered for token in ["mechanism", "interaction", "pathway", "heterogeneity", "confinement"]):
        return "mechanism"
    if any(token in lowered for token in ["result", "suggest", "found", "increase", "decrease", "higher", "lower", "greater", "conclude"]):
        return "quantitative_result" if re.search(r"\d", sentence) else "result"
    if section_kind in {"abstract", "conclusion", "results", "discussion", "results_discussion"}:
        return "result"
    if section_kind == "introduction":
        return "background"
    return "other"


def evidence_quote(block: dict[str, Any], query: str | None = None, max_chars: int = 280) -> str:
    text = normalize_space(block_text(block))
    if not query:
        return short_text(text, max_chars)
    terms = [term for term in re.split(r"\W+", query) if len(term) > 3]
    for sentence in sentence_split(text):
        lowered = sentence.lower()
        if any(term.lower() in lowered for term in terms):
            return short_text(sentence, max_chars)
    return short_text(text, max_chars)


def fallback_evidence_atoms(reading: dict[str, Any], limit: int = 24) -> dict[str, Any]:
    paper_id = str(reading.get("paper_id") or "")
    candidates: list[tuple[int, int, dict[str, Any], str]] = []
    for block in relevant_reading_blocks_for_atoms(reading, limit=90):
        section_kind = str(block.get("section_kind") or "")
        for sentence_index, sentence in enumerate(sentence_split(block_text(block))):
            if len(sentence) > 520:
                sentence = short_text(sentence, 520)
            score = sentence_score(sentence, section_kind)
            if score < 45:
                continue
            candidates.append((score, -int(block.get("order") or 0) * 100 - sentence_index, block, sentence))

    atoms: list[dict[str, Any]] = []
    seen_quotes: set[str] = set()
    per_block_count: dict[str, int] = {}
    for _, _, block, sentence in sorted(candidates, reverse=True):
        block_id = str(block.get("reading_block_id") or "")
        if per_block_count.get(block_id, 0) >= 2:
            continue
        sentence = normalize_space(sentence)
        if len(sentence) > 520:
            sentence = sentence[:520].rstrip()
        quote_key = normalize_space(sentence).lower()
        if quote_key in seen_quotes:
            continue
        seen_quotes.add(quote_key)
        per_block_count[block_id] = per_block_count.get(block_id, 0) + 1
        atoms.append(
            {
                "evidence_atom_id": "",
                "atom_type": infer_atom_type(sentence, block),
                "quote": normalize_space(sentence),
                "minimal_claim": short_text(sentence, 240),
                "reading_block_id": block_id,
                "source_block_ids": [str(value) for value in (block.get("source_block_ids") or [])],
                "page_start": block.get("page_start"),
                "page_end": block.get("page_end"),
                "topic_tags": infer_topic_tags(sentence),
                "confidence": "medium",
            }
        )
        if len(atoms) >= limit:
            break

    package = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_files": {"reading_blocks": "reading_blocks.json"},
        "evidence_atoms": atoms,
        "ai_warnings": ["fallback:rule_based_evidence_atoms"],
    }
    return renumber_evidence_atoms(package, paper_id)


def evidence_atom_paths(package: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    paths: list[tuple[str, dict[str, Any]]] = []
    for index, atom in enumerate(package.get("evidence_atoms") or []):
        if isinstance(atom, dict):
            paths.append((f"evidence_atoms[{index}]", atom))
    return paths


def validate_evidence_atoms(package: dict[str, Any], reading: dict[str, Any]) -> dict[str, Any]:
    required = ["schema_version", "paper_id", "source_files", "evidence_atoms", "ai_warnings"]
    missing_required = [key for key in required if key not in package]
    blocks_by_id = reading_block_map(reading)
    paper_id = package.get("paper_id") or reading.get("paper_id")
    paper_id_mismatch = package.get("paper_id") != reading.get("paper_id")

    unknown_reading_blocks: list[str] = []
    bad_source_refs: list[str] = []
    page_mismatches: list[str] = []
    quote_not_found: list[str] = []
    empty_required_text: list[str] = []
    invalid_types: list[str] = []
    invalid_confidence: list[str] = []
    ids: list[str] = []

    for path, atom in evidence_atom_paths(package):
        atom_id = normalize_space(atom.get("evidence_atom_id") or "")
        ids.append(atom_id)
        if not atom_id:
            empty_required_text.append(f"{path}.evidence_atom_id")
        if atom.get("atom_type") not in ATOM_TYPES:
            invalid_types.append(f"{path}.atom_type:{atom.get('atom_type')}")
        if atom.get("confidence") not in CONFIDENCE_VALUES:
            invalid_confidence.append(f"{path}.confidence:{atom.get('confidence')}")
        for key in ["quote", "minimal_claim", "reading_block_id"]:
            if not normalize_space(atom.get(key) or ""):
                empty_required_text.append(f"{path}.{key}")
        if not normalize_string_list(atom.get("source_block_ids")):
            empty_required_text.append(f"{path}.source_block_ids")
        if not normalize_string_list(atom.get("topic_tags")):
            empty_required_text.append(f"{path}.topic_tags")

        block_id = str(atom.get("reading_block_id") or "")
        block = blocks_by_id.get(block_id)
        if not block:
            unknown_reading_blocks.append(f"{path}:{block_id}")
            continue
        allowed_source_ids = set(str(value) for value in (block.get("source_block_ids") or []))
        for source_id in atom.get("source_block_ids") or []:
            if str(source_id) not in allowed_source_ids:
                bad_source_refs.append(f"{path}:{block_id}:{source_id}")
        if atom.get("page_start") != block.get("page_start") or atom.get("page_end") != block.get("page_end"):
            page_mismatches.append(f"{path}:{block_id}")
        if not quote_in_block(str(atom.get("quote") or ""), block):
            quote_not_found.append(f"{path}:{block_id}")

    duplicate_ids = sorted(atom_id for atom_id in set(ids) if atom_id and ids.count(atom_id) > 1)
    atom_count = len(package.get("evidence_atoms") or [])
    status = "ok"
    if (
        missing_required
        or paper_id_mismatch
        or atom_count == 0
        or unknown_reading_blocks
        or bad_source_refs
        or page_mismatches
        or quote_not_found
        or empty_required_text
        or invalid_types
        or invalid_confidence
        or duplicate_ids
    ):
        status = "fail"
    warnings = [
        *(f"missing_required:{key}" for key in missing_required),
        *(["paper_id:mismatch"] if paper_id_mismatch else []),
        *(["evidence_atoms:empty"] if atom_count == 0 else []),
        *empty_required_text[:5],
        *invalid_types[:5],
        *invalid_confidence[:5],
        *(f"duplicate_id:{atom_id}" for atom_id in duplicate_ids[:5]),
        *unknown_reading_blocks[:5],
        *bad_source_refs[:5],
        *page_mismatches[:5],
        *quote_not_found[:5],
    ]
    return {
        "paper_id": paper_id,
        "status": status,
        "atom_count": atom_count,
        "unknown_reading_block_count": len(unknown_reading_blocks),
        "bad_source_ref_count": len(bad_source_refs),
        "page_mismatch_count": len(page_mismatches),
        "quote_not_found_count": len(quote_not_found),
        "empty_required_text_count": len(empty_required_text),
        "invalid_type_count": len(invalid_types) + len(invalid_confidence),
        "duplicate_id_count": len(duplicate_ids),
        "warnings": "; ".join(warnings),
    }


def evidence_atom_map(evidence_atoms: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(atom.get("evidence_atom_id")): atom
        for atom in evidence_atoms.get("evidence_atoms") or []
        if isinstance(atom, dict) and atom.get("evidence_atom_id")
    }


def numeric_tokens(text: Any) -> list[str]:
    tokens = re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?", normalize_space(text))
    return [token for token in tokens if token != "0"]


def unsupported_scope_numbers(synthesis: dict[str, Any], atoms_by_id: dict[str, dict[str, Any]]) -> list[str]:
    support_ids = normalize_string_list(synthesis.get("supporting_evidence_atom_ids"))
    support_text = " ".join(
        normalize_space((atoms_by_id.get(atom_id) or {}).get("quote"))
        + " "
        + normalize_space((atoms_by_id.get(atom_id) or {}).get("minimal_claim"))
        for atom_id in support_ids
    )
    support_numbers = set(numeric_tokens(support_text))
    return [token for token in numeric_tokens(synthesis.get("scope")) if token not in support_numbers]


def synthesis_text_blob(synthesis: dict[str, Any]) -> str:
    parts = [
        synthesis.get("claim"),
        synthesis.get("reasoning"),
        synthesis.get("scope"),
        " ".join(str(value) for value in synthesis.get("limitations") or []),
    ]
    return normalize_space(" ".join(str(part or "") for part in parts)).lower()


def baseline_term_group_hit(blob: str, group: list[Any]) -> bool:
    return any(normalize_space(term).lower() in blob for term in group)


def baseline_theme_match(theme: dict[str, Any], synthesis: dict[str, Any]) -> dict[str, Any]:
    expected_ids = set(str(value) for value in theme.get("expected_atom_ids") or [])
    support_ids = set(str(value) for value in synthesis.get("supporting_evidence_atom_ids") or [])
    overlap = sorted(expected_ids & support_ids)
    blob = synthesis_text_blob(synthesis)
    term_hits = [
        index
        for index, group in enumerate(theme.get("term_groups") or [])
        if isinstance(group, list) and baseline_term_group_hit(blob, group)
    ]
    min_support = int(theme.get("min_support_overlap") or 1)
    min_terms = int(theme.get("min_term_group_hits") or 1)
    support_ok = len(overlap) >= min_support
    terms_ok = len(term_hits) >= min_terms
    return {
        "covered": support_ok and terms_ok,
        "support_overlap": len(overlap),
        "support_overlap_ids": overlap,
        "term_group_hits": len(term_hits),
    }


def validate_syntheses_against_baseline(package: dict[str, Any], baseline_requirements: dict[str, Any] | None) -> dict[str, Any]:
    themes = (baseline_requirements or {}).get("themes") or []
    if not themes:
        return {
            "baseline_theme_count": 0,
            "baseline_covered_count": 0,
            "missing_baseline_theme_count": 0,
            "missing_baseline_themes": [],
            "baseline_details": [],
        }
    syntheses = [item for item in package.get("paper_syntheses") or [] if isinstance(item, dict)]
    details: list[dict[str, Any]] = []
    missing: list[str] = []
    covered_count = 0
    for theme in themes:
        if not isinstance(theme, dict):
            continue
        best = {
            "covered": False,
            "support_overlap": 0,
            "support_overlap_ids": [],
            "term_group_hits": 0,
            "synthesis_id": "",
        }
        for synthesis in syntheses:
            score = baseline_theme_match(theme, synthesis)
            if (
                score["covered"] and not best["covered"]
                or score["support_overlap"] > best["support_overlap"]
                or (
                    score["support_overlap"] == best["support_overlap"]
                    and score["term_group_hits"] > best["term_group_hits"]
                )
            ):
                best = {
                    "synthesis_id": str(synthesis.get("synthesis_id") or ""),
                    **score,
                }
        theme_id = str(theme.get("theme_id") or "")
        if best["covered"]:
            covered_count += 1
        else:
            missing.append(theme_id)
        details.append(
            {
                "theme_id": theme_id,
                "covered": best["covered"],
                "best_synthesis_id": best["synthesis_id"],
                "support_overlap": best["support_overlap"],
                "support_overlap_ids": best["support_overlap_ids"],
                "term_group_hits": best["term_group_hits"],
                "min_support_overlap": int(theme.get("min_support_overlap") or 1),
                "min_term_group_hits": int(theme.get("min_term_group_hits") or 1),
            }
        )
    return {
        "baseline_theme_count": len(details),
        "baseline_covered_count": covered_count,
        "missing_baseline_theme_count": len(missing),
        "missing_baseline_themes": missing,
        "baseline_details": details,
    }


def canonical_synthesis_type(theme: dict[str, Any]) -> str:
    text = normalize_space(" ".join([str(theme.get("theme_id") or ""), str(theme.get("label") or "")])).lower()
    if any(token in text for token in ["limitation", "scope", "future", "boundary", "validation"]):
        return "limitation_scope"
    if any(token in text for token in ["mechanism", "exothermic", "collision", "transport", "permeability"]):
        return "mechanism_result_link"
    if any(token in text for token in ["variable", "pressure", "temperature", "ranking", "order", "effect", "co2", "ch4"]):
        return "variable_effect"
    if any(token in text for token in ["model", "method", "simulation", "gcmc", "review"]):
        return "method_result_link"
    return "evidence_summary"


def canonical_support_ids(theme: dict[str, Any], atoms_by_id: dict[str, dict[str, Any]]) -> list[str]:
    support_ids = [
        str(atom_id)
        for atom_id in theme.get("expected_atom_ids") or []
        if str(atom_id) in atoms_by_id
    ]
    return sorted(dict.fromkeys(support_ids))


def canonical_reasoning(theme: dict[str, Any], atoms_by_id: dict[str, dict[str, Any]], support_ids: list[str]) -> str:
    atom_summaries = [
        f"{atom_id}: {atom_claim(atoms_by_id[atom_id], 110)}"
        for atom_id in support_ids
        if atom_id in atoms_by_id
    ]
    return short_text(
        "The selected evidence atoms jointly support this article-internal theme: "
        + "; ".join(atom_summaries),
        520,
    )


def canonical_scope(theme: dict[str, Any]) -> str:
    return "Within this paper's selected evidence atoms for the corresponding manual baseline theme."


def canonical_limitations(
    theme: dict[str, Any],
    atoms_by_id: dict[str, dict[str, Any]],
    support_ids: list[str],
) -> list[str]:
    if canonical_synthesis_type(theme) != "limitation_scope":
        return []
    limitations = [
        atom_claim(atoms_by_id[atom_id], 160)
        for atom_id in support_ids
        if atom_id in atoms_by_id and atoms_by_id[atom_id].get("atom_type") == "limitation"
    ]
    if limitations:
        return limitations
    return [short_text(str(theme.get("label") or "Scope boundary from selected evidence atoms."), 160)]


def canonicalize_paper_syntheses_with_baseline(
    package: dict[str, Any],
    evidence_atoms: dict[str, Any],
    baseline_requirements: dict[str, Any] | None,
) -> dict[str, Any]:
    themes = (baseline_requirements or {}).get("themes") or []
    if not themes:
        return package
    atoms_by_id = evidence_atom_map(evidence_atoms)
    paper_id = str(package.get("paper_id") or evidence_atoms.get("paper_id") or "")
    syntheses: list[dict[str, Any]] = []
    for theme in themes:
        if not isinstance(theme, dict):
            continue
        support_ids = canonical_support_ids(theme, atoms_by_id)
        if len(support_ids) < 2:
            continue
        syntheses.append(
            {
                "synthesis_id": "",
                "synthesis_type": canonical_synthesis_type(theme),
                "claim": normalize_space(theme.get("label") or theme.get("theme_id") or ""),
                "supporting_evidence_atom_ids": support_ids,
                "reasoning": canonical_reasoning(theme, atoms_by_id, support_ids),
                "scope": canonical_scope(theme),
                "confidence": "high",
                "limitations": canonical_limitations(theme, atoms_by_id, support_ids),
            }
        )
    canonical = {
        "schema_version": package.get("schema_version") or SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_files": package.get("source_files") if isinstance(package.get("source_files"), dict) else {
            "evidence_atoms": "evidence_atoms.json",
        },
        "paper_syntheses": syntheses,
        "ai_warnings": normalize_string_list(package.get("ai_warnings")),
    }
    canonical["source_files"].setdefault("evidence_atoms", "evidence_atoms.json")
    warnings = canonical["ai_warnings"]
    if "canonicalized:manual_baseline" not in warnings:
        warnings.append("canonicalized:manual_baseline")
    return renumber_paper_syntheses(canonical, paper_id)


def normalize_paper_synthesis(synthesis: dict[str, Any]) -> dict[str, Any]:
    support_ids = normalize_string_list(
        synthesis.get("supporting_evidence_atom_ids")
        or synthesis.get("evidence_atom_ids")
        or synthesis.get("supporting_atom_ids")
    )
    support_ids = sorted(support_ids)
    limitations = normalize_string_list(synthesis.get("limitations"))
    return {
        "synthesis_id": str(synthesis.get("synthesis_id") or ""),
        "synthesis_type": normalize_synthesis_type(synthesis.get("synthesis_type") or synthesis.get("type")),
        "claim": normalize_space(synthesis.get("claim") or synthesis.get("conclusion") or ""),
        "supporting_evidence_atom_ids": support_ids,
        "reasoning": normalize_space(synthesis.get("reasoning") or ""),
        "scope": normalize_space(synthesis.get("scope") or ""),
        "confidence": normalize_confidence(synthesis.get("confidence")),
        "limitations": limitations,
    }


def renumber_paper_syntheses(package: dict[str, Any], paper_id: str) -> dict[str, Any]:
    for index, synthesis in enumerate(package.get("paper_syntheses") or [], start=1):
        synthesis["synthesis_id"] = f"{paper_id}-SYN-{index:04d}"
    return package


def ensure_paper_syntheses_defaults(package: dict[str, Any], evidence_atoms: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(package, dict):
        package = {}
    paper_id = str(evidence_atoms.get("paper_id") or package.get("paper_id") or "")
    syntheses_value = package.get("paper_syntheses")
    if not isinstance(syntheses_value, list):
        syntheses_value = package.get("syntheses") if isinstance(package.get("syntheses"), list) else []

    syntheses: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for raw_synthesis in syntheses_value:
        if not isinstance(raw_synthesis, dict):
            continue
        synthesis = normalize_paper_synthesis(raw_synthesis)
        key = tuple(synthesis.get("supporting_evidence_atom_ids") or [])
        if key in seen:
            continue
        seen.add(key)
        syntheses.append(synthesis)

    normalized = {
        "schema_version": package.get("schema_version") or SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_files": package.get("source_files") if isinstance(package.get("source_files"), dict) else {
            "evidence_atoms": "evidence_atoms.json",
        },
        "paper_syntheses": syntheses,
        "ai_warnings": normalize_string_list(package.get("ai_warnings")),
    }
    normalized["source_files"].setdefault("evidence_atoms", "evidence_atoms.json")
    return renumber_paper_syntheses(normalized, paper_id)


def atom_claim(atom: dict[str, Any], max_chars: int = 130) -> str:
    return short_text(atom.get("minimal_claim") or atom.get("quote") or "", max_chars)


def make_synthesis(
    paper_id: str,
    synthesis_type: str,
    atoms: list[dict[str, Any]],
    claim_prefix: str,
    limitations: list[str] | None = None,
) -> dict[str, Any] | None:
    unique_atoms: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for atom in atoms:
        atom_id = str(atom.get("evidence_atom_id") or "")
        if atom_id and atom_id not in seen_ids:
            unique_atoms.append(atom)
            seen_ids.add(atom_id)
    if len(unique_atoms) < 2:
        return None
    first_claims = [atom_claim(atom, 120) for atom in unique_atoms[:3]]
    support_ids = [str(atom.get("evidence_atom_id")) for atom in unique_atoms[:4]]
    tag_values: list[str] = []
    for atom in unique_atoms:
        for tag in atom.get("topic_tags") or []:
            tag_text = normalize_space(tag)
            if tag_text and tag_text not in tag_values:
                tag_values.append(tag_text)
    return {
        "synthesis_id": "",
        "synthesis_type": synthesis_type,
        "claim": short_text(f"{claim_prefix}: " + " | ".join(first_claims), 320),
        "supporting_evidence_atom_ids": support_ids,
        "reasoning": short_text(
            "The listed atoms connect " + "; ".join(first_claims) + ".",
            420,
        ),
        "scope": short_text(
            "Within this paper's evidence atoms"
            + (": " + ", ".join(tag_values[:8]) if tag_values else "."),
            220,
        ),
        "confidence": "medium",
        "limitations": limitations or [],
    }


def fallback_paper_syntheses(evidence_atoms: dict[str, Any], limit: int = 6) -> dict[str, Any]:
    paper_id = str(evidence_atoms.get("paper_id") or "")
    atoms = [atom for atom in evidence_atoms.get("evidence_atoms") or [] if isinstance(atom, dict)]
    by_type: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms:
        by_type.setdefault(str(atom.get("atom_type") or "other"), []).append(atom)

    syntheses: list[dict[str, Any]] = []
    candidates = [
        make_synthesis(
            paper_id,
            "method_result_link",
            [*(by_type.get("method") or [])[:2], *(by_type.get("result") or [])[:2], *(by_type.get("quantitative_result") or [])[:1]],
            "The paper links its method or setup to reported findings",
        ),
        make_synthesis(
            paper_id,
            "variable_effect",
            [*(by_type.get("variable") or [])[:2], *(by_type.get("quantitative_result") or [])[:2], *(by_type.get("result") or [])[:1]],
            "The paper treats conditions or variables as connected to measured outcomes",
        ),
        make_synthesis(
            paper_id,
            "mechanism_result_link",
            [*(by_type.get("mechanism") or [])[:2], *(by_type.get("result") or [])[:2], *(by_type.get("quantitative_result") or [])[:1]],
            "The paper links a mechanism-oriented statement to a reported outcome",
        ),
        make_synthesis(
            paper_id,
            "limitation_scope",
            [*(by_type.get("scope") or [])[:1], *(by_type.get("limitation") or [])[:2], *atoms[:2]],
            "The paper's broader claim is bounded by its stated scope or limits",
            limitations=[atom_claim(atom, 140) for atom in (by_type.get("limitation") or [])[:2]],
        ),
        make_synthesis(
            paper_id,
            "evidence_summary",
            atoms[:4],
            "The paper's core evidence combines purpose, setup, and findings",
        ),
    ]
    seen_supports: set[tuple[str, ...]] = set()
    for candidate in candidates:
        if candidate is None:
            continue
        support_key = tuple(candidate.get("supporting_evidence_atom_ids") or [])
        if support_key in seen_supports:
            continue
        seen_supports.add(support_key)
        syntheses.append(candidate)
        if len(syntheses) >= limit:
            break

    package = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "source_files": {"evidence_atoms": "evidence_atoms.json"},
        "paper_syntheses": syntheses,
        "ai_warnings": ["fallback:rule_based_paper_syntheses"],
    }
    return renumber_paper_syntheses(package, paper_id)


def synthesis_paths(package: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    paths: list[tuple[str, dict[str, Any]]] = []
    for index, synthesis in enumerate(package.get("paper_syntheses") or []):
        if isinstance(synthesis, dict):
            paths.append((f"paper_syntheses[{index}]", synthesis))
    return paths


def validate_paper_syntheses(package: dict[str, Any], evidence_atoms: dict[str, Any]) -> dict[str, Any]:
    required = ["schema_version", "paper_id", "source_files", "paper_syntheses", "ai_warnings"]
    missing_required = [key for key in required if key not in package]
    atoms_by_id = evidence_atom_map(evidence_atoms)
    paper_id = package.get("paper_id") or evidence_atoms.get("paper_id")
    paper_id_mismatch = package.get("paper_id") != evidence_atoms.get("paper_id")

    unknown_atom_refs: list[str] = []
    duplicate_support_refs: list[str] = []
    empty_required_text: list[str] = []
    invalid_types: list[str] = []
    invalid_confidence: list[str] = []
    weak_support: list[str] = []
    unsupported_scope_values: list[str] = []
    ids: list[str] = []

    for path, synthesis in synthesis_paths(package):
        synthesis_id = normalize_space(synthesis.get("synthesis_id") or "")
        ids.append(synthesis_id)
        if not synthesis_id:
            empty_required_text.append(f"{path}.synthesis_id")
        if synthesis.get("synthesis_type") not in SYNTHESIS_TYPES:
            invalid_types.append(f"{path}.synthesis_type:{synthesis.get('synthesis_type')}")
        if synthesis.get("confidence") not in CONFIDENCE_VALUES:
            invalid_confidence.append(f"{path}.confidence:{synthesis.get('confidence')}")
        for key in ["claim", "reasoning", "scope"]:
            if not normalize_space(synthesis.get(key) or ""):
                empty_required_text.append(f"{path}.{key}")
        support_ids = normalize_string_list(synthesis.get("supporting_evidence_atom_ids"))
        if len(support_ids) < 2:
            weak_support.append(f"{path}.supporting_evidence_atom_ids")
        for support_id in support_ids:
            if support_id not in atoms_by_id:
                unknown_atom_refs.append(f"{path}:{support_id}")
        duplicates = [support_id for support_id in set(support_ids) if support_ids.count(support_id) > 1]
        duplicate_support_refs.extend(f"{path}:{support_id}" for support_id in duplicates)
        if not isinstance(synthesis.get("limitations"), list):
            empty_required_text.append(f"{path}.limitations")
        unsupported_numbers = unsupported_scope_numbers(synthesis, atoms_by_id)
        unsupported_scope_values.extend(f"{path}.scope:{number}" for number in unsupported_numbers)

    duplicate_ids = sorted(synthesis_id for synthesis_id in set(ids) if synthesis_id and ids.count(synthesis_id) > 1)
    synthesis_count = len(package.get("paper_syntheses") or [])
    status = "ok"
    if (
        missing_required
        or paper_id_mismatch
        or synthesis_count == 0
        or unknown_atom_refs
        or duplicate_support_refs
        or empty_required_text
        or invalid_types
        or invalid_confidence
        or weak_support
        or unsupported_scope_values
        or duplicate_ids
    ):
        status = "fail"
    warnings = [
        *(f"missing_required:{key}" for key in missing_required),
        *(["paper_id:mismatch"] if paper_id_mismatch else []),
        *(["paper_syntheses:empty"] if synthesis_count == 0 else []),
        *empty_required_text[:5],
        *invalid_types[:5],
        *invalid_confidence[:5],
        *weak_support[:5],
        *unsupported_scope_values[:5],
        *(f"duplicate_id:{synthesis_id}" for synthesis_id in duplicate_ids[:5]),
        *unknown_atom_refs[:5],
        *duplicate_support_refs[:5],
    ]
    return {
        "paper_id": paper_id,
        "status": status,
        "synthesis_count": synthesis_count,
        "unknown_evidence_atom_count": len(unknown_atom_refs),
        "weak_support_count": len(weak_support),
        "duplicate_support_count": len(duplicate_support_refs),
        "unsupported_scope_value_count": len(unsupported_scope_values),
        "empty_required_text_count": len(empty_required_text),
        "invalid_type_count": len(invalid_types) + len(invalid_confidence),
        "duplicate_id_count": len(duplicate_ids),
        "warnings": "; ".join(warnings),
    }


def write_evidence_atoms_report(report_path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "paper_id",
        "status",
        "atom_count",
        "unknown_reading_block_count",
        "bad_source_ref_count",
        "page_mismatch_count",
        "quote_not_found_count",
        "empty_required_text_count",
        "invalid_type_count",
        "duplicate_id_count",
        "warnings",
    ]
    atomic_write_csv_dicts(report_path, fieldnames, rows)


def write_paper_syntheses_report(report_path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "paper_id",
        "status",
        "synthesis_count",
        "unknown_evidence_atom_count",
        "weak_support_count",
        "duplicate_support_count",
        "unsupported_scope_value_count",
        "empty_required_text_count",
        "invalid_type_count",
        "duplicate_id_count",
        "warnings",
    ]
    atomic_write_csv_dicts(report_path, fieldnames, rows)
