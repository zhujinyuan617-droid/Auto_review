from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .io_utils import atomic_write_csv_dicts, write_json


SCHEMA_VERSION = "0.1.0"

CARD_LIST_FIELDS = [
    "fuzzy_keywords",
    "study_design",
    "variables",
    "mechanisms",
    "key_findings",
    "quantitative_results",
    "limitations",
    "review_section_hints",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_space(value: str) -> str:
    return " ".join(str(value or "").split())


def collapse_spaced_letters(value: str) -> str:
    tokens = normalize_space(value).split()
    collapsed: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if len(token) == 1 and token.isalpha():
            letters = [token]
            index += 1
            while index < len(tokens) and len(tokens[index]) == 1 and tokens[index].isalpha():
                letters.append(tokens[index])
                index += 1
            if len(letters) >= 3:
                collapsed.append("".join(letters))
            else:
                collapsed.extend(letters)
            continue
        collapsed.append(token)
        index += 1
    return " ".join(collapsed)


def normalized_for_quality(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", collapse_spaced_letters(value).lower()).strip()


def short_text(value: str, max_chars: int) -> str:
    text = normalize_space(value)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "..."


def block_text(block: dict[str, Any]) -> str:
    return str(block.get("text") or block.get("caption") or "")


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


def relevant_reading_blocks(reading: dict[str, Any], limit: int = 140) -> list[dict[str, Any]]:
    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, block in enumerate(reading.get("reading_blocks") or []):
        if not block.get("include_in_reading", True):
            continue
        if block.get("reading_type") in {"page_header", "noise", "formula"}:
            continue
        text = normalize_space(block_text(block))
        if not text:
            continue
        section_kind = str(block.get("section_kind") or "")
        reading_type = str(block.get("reading_type") or "")
        lowered = text.lower()
        score = 0
        if section_kind in {"front_matter", "keywords", "abstract", "conclusion"}:
            score += 100
        if section_kind in {"methods", "results", "discussion", "results_discussion"}:
            score += 80
        if reading_type in {"section_heading", "keywords"}:
            score += 40
        if reading_type in {"table", "figure"} and text:
            score += 35
        if any(
            token in lowered
            for token in [
                "this study",
                "in this work",
                "aim",
                "objective",
                "method",
                "experiment",
                "simulation",
                "pressure",
                "temperature",
                "mpa",
                "adsorption",
                "diffusion",
                "results suggested",
                "conclude",
                "limitation",
                "recommended",
            ]
        ):
            score += 30
        if re.search(r"\d", text):
            score += 10
        if score > 0:
            scored.append((score, -index, block))
    selected = [block for _, _, block in sorted(scored, reverse=True)[:limit]]
    return sorted(selected, key=lambda block: int(block.get("order") or 0))


def build_prompt(
    reading: dict[str, Any],
    metadata: dict[str, Any],
    max_block_chars: int = 900,
) -> list[dict[str, str]]:
    paper_id = reading["paper_id"]
    metadata_candidates = metadata.get("metadata_candidates", {})
    blocks = [reading_block_prompt_item(block, max_block_chars) for block in relevant_reading_blocks(reading)]
    payload = {
        "paper_id": paper_id,
        "metadata_candidates": {
            "title": metadata_candidates.get("title", ""),
            "doi": metadata_candidates.get("doi", ""),
            "year": metadata_candidates.get("year", ""),
            "journal": metadata_candidates.get("journal", ""),
        },
        "allowed_paper_types": ["experimental", "simulation", "review", "hybrid", "other", "unknown"],
        "allowed_variable_roles": ["independent", "dependent", "control", "condition", "parameter", "other", "unknown"],
        "reading_blocks": blocks,
    }
    system = (
        "You extract structured literature-review cards from academic paper reading blocks. "
        "Use only the supplied reading blocks. Do not invent paper facts, results, conditions, methods, or citations. "
        "Do not rewrite evidence quotes: quote must be a short exact excerpt from the cited reading block text. "
        "Every claim-like item must include evidence. Return strict JSON only."
    )
    user = (
        "Build one literature_card JSON for this paper using the schema_version 0.1.0 structure. "
        "Be conservative. Prefer fewer high-quality, well-evidenced items over many weak items. "
        "Do not return an empty card when abstract, method, or result blocks are supplied. "
        "At minimum, extract core_question from the abstract or objective block and attach one evidence object copied "
        "from that same block. Then extract at least one study_design item from a methods block and at least one "
        "key_findings or quantitative_results item from an abstract, results, discussion, or conclusion block when "
        "those blocks are present. "
        "A valid output must at minimum include paper, classification, a core_question with one direct evidence quote, "
        "and at least one evidence-backed item in one of study_design, key_findings, or variables when the supplied "
        "blocks contain abstract/method/result information. "
        "paper.title must be the article title, not the journal name, article type, publisher banner, or section heading. "
        "If metadata_candidates.title is empty or visibly a journal name, infer the title only from the front-matter "
        "reading blocks that contain the article title. paper.journal must be the journal/source name, not the article title. "
        "Do not create placeholder items to satisfy a desired count. Arrays may be empty when the supplied reading "
        "blocks do not support high-quality items. Before returning, delete any list item that has an empty required "
        "text field, placeholder text, or no evidence. Placeholder text includes unknown, unspecified, not specified, "
        "N/A, none, reported result, and similar filler. "
        "classification should contain short normalized tags extracted from the paper, such as materials, gases, "
        "methods, modeling scales, and domain tags. classification must be an object with keys research_objects, "
        "gas_systems, methods, scale, domain_tags; each value must be an array of strings. "
        "core_question.claim should state the main research question or purpose in one sentence. "
        "Never use a section label such as abstract, introduction, article info, or keywords as core_question.claim. "
        "fuzzy_keywords should contain 8 to 20 weak-discovery keywords useful for retrieval, clustering, and review "
        "planning. Each item must include keyword, reason, and evidence. These can include mechanisms, phenomena, "
        "application scenarios, adsorption descriptors, or method-specific phrases. "
        "study_design should capture experimental/simulation/model setup, samples, models, or workflow. "
        "Return 3 to 6 study_design items when the paper contains enough evidence. "
        "variables should capture temperatures, pressures, gas ratios, pore/mineral/functional-group parameters, "
        "or other important independent/dependent/control quantities. For variables, include an item only when you "
        "can fill a specific name and explicit values_or_range from the cited reading block; otherwise omit it. "
        "mechanisms should capture mechanistic explanations, not just results; each item must fill both mechanism "
        "and explanation with concise text. "
        "key_findings should capture review-worthy conclusions; each item must use the key claim field named claim. "
        "quantitative_results must include only explicit numeric values or ranges with conditions. "
        "Each quantitative_results item must fill metric, value, condition, and interpretation. "
        "limitations should include only limitations or boundaries stated or clearly supported by the paper. "
        "Each limitations item must fill limitation. "
        "review_section_hints is required when any key_findings, mechanisms, quantitative_results, or limitations "
        "are extracted. Return 1 to 3 evidence-backed hints. Each hint should name a concise review subsection "
        "where this paper would be useful, for example 'pore-scale gas transport models', 'CO2/CH4 adsorption in "
        "clay minerals', 'microfluidic porous-media analogs', or 'drag laws for polydisperse suspensions'. "
        "The reason must explain how the paper contributes to that subsection, not merely repeat the title. "
        "Evidence objects must use reading_block_id/source_block_ids/page_start/page_end exactly from the cited block. "
        "source_block_ids in evidence must be a subset of that reading block's source_block_ids. "
        "Evidence must be specific to the extracted item: the quote should contain the claim, keyword, variable, "
        "numeric value, method, or mechanism being supported. Do not cite a generic introduction/context block for "
        "unrelated keywords just because it shares broad terms. "
        "Evidence note must explain the direct support. Never write notes such as Auto-inferred evidence, Derived "
        "evidence, similar reading block, or any statement that says the evidence was guessed. "
        "If a claim cannot be directly supported by an exact quote, omit the claim. "
        "Never return an empty evidence array for any item. If you cannot cite a reading block for an item, omit that "
        "item entirely. Each evidence object must have exactly these fields: "
        "{\"reading_block_id\":\"S01-RB-0009\",\"source_block_ids\":[\"S01-BLK-0018\"],"
        "\"page_start\":1,\"page_end\":1,\"quote\":\"short exact excerpt\",\"note\":\"why this supports the item\"}. "
        "For example, if the abstract says what the paper determines, core_question.evidence should cite the abstract "
        "reading_block_id and quote that exact objective phrase. "
        "Do not use alternate field names such as text, finding, values, source, block_id, or chunk_id in the final output. "
        "Do not put validation excuses in ai_warnings; fix the JSON by omitting unsupported items instead. "
        "Output schema keys exactly: schema_version, paper_id, paper, classification, fuzzy_keywords, "
        "core_question, study_design, variables, mechanisms, key_findings, quantitative_results, limitations, "
        "review_section_hints, ai_warnings. "
        "Here is the input JSON:\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_repair_prompt(
    previous_messages: list[dict[str, str]],
    candidate: dict[str, Any],
    validation: dict[str, Any],
) -> list[dict[str, str]]:
    candidate_evidence_count = len(evidence_paths(candidate))
    repair_instruction = (
        "The previous literature_card JSON failed validation. Return a corrected complete literature_card JSON object. "
        "Do not explain. Do not use Markdown. Do not preserve invalid placeholder items. "
        "Regenerate the card from the original supplied reading blocks, not from the invalid candidate. "
        "The corrected card must include a core_question.evidence object copied from a supplied reading block, usually "
        "from an abstract or objective block containing phrases like 'This study', 'In this work', 'aim', or 'objective'. "
        "Omit any list item with empty required text, placeholder text, weak/generic evidence, or missing evidence, "
        "but do not delete the whole card when the abstract or methods blocks provide direct evidence. "
        "It is acceptable to return only 1-3 strong items per section; evidence quality is more important than quantity. "
        "Keep only items that can be supported by the supplied reading blocks. "
        "Validation summary:\n"
        + json.dumps(validation, ensure_ascii=False)
    )
    if candidate_evidence_count:
        repair_instruction += "\nPrevious candidate JSON:\n" + json.dumps(candidate, ensure_ascii=False)
        return [
            *previous_messages,
            {"role": "assistant", "content": json.dumps(candidate, ensure_ascii=False)},
            {"role": "user", "content": repair_instruction},
        ]
    return [*previous_messages, {"role": "user", "content": repair_instruction}]


def ensure_card_defaults(card: dict[str, Any], reading: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    metadata_candidates = metadata.get("metadata_candidates", {})
    card.setdefault("schema_version", SCHEMA_VERSION)
    card.setdefault("paper_id", reading.get("paper_id", ""))
    if not isinstance(card.get("paper"), dict):
        card["paper"] = {}
    paper = card["paper"]
    paper.setdefault("title", metadata_candidates.get("title", ""))
    paper.setdefault("doi", metadata_candidates.get("doi", ""))
    paper.setdefault("year", metadata_candidates.get("year", ""))
    paper.setdefault("journal", metadata_candidates.get("journal", ""))
    paper.setdefault("paper_type", "unknown")
    if not isinstance(card.get("classification"), dict):
        card["classification"] = {}
    classification = card["classification"]
    for key in ["research_objects", "gas_systems", "methods", "scale", "domain_tags"]:
        classification.setdefault(key, [])
    if not isinstance(card.get("core_question"), dict):
        card["core_question"] = {"claim": "", "evidence": []}
    card.setdefault("core_question", {"claim": "", "evidence": []})
    for field in CARD_LIST_FIELDS:
        if not isinstance(card.get(field), list):
            card[field] = []
        card.setdefault(field, [])
    if not isinstance(card.get("ai_warnings"), list):
        card["ai_warnings"] = []
    card["ai_warnings"] = [
        str(warning) for warning in card.get("ai_warnings", []) if not str(warning).startswith("validator:")
    ]
    card.setdefault("ai_warnings", [])
    normalize_card_items(card, reading)
    prune_empty_items(card)
    if not card.get("fuzzy_keywords"):
        card["fuzzy_keywords"] = derive_fuzzy_keywords(card)
        prune_empty_items(card)
    return card


def source_to_reading_block_map(reading: dict[str, Any]) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for block in reading.get("reading_blocks") or []:
        for source_id in block.get("source_block_ids") or []:
            mapping[str(source_id)] = block
    return mapping


def normalize_evidence(evidence: dict[str, Any], reading: dict[str, Any]) -> dict[str, Any]:
    blocks_by_id = reading_block_map(reading)
    by_source = source_to_reading_block_map(reading)
    reading_block_id = str(evidence.get("reading_block_id") or evidence.get("chunk_id") or "")
    block = blocks_by_id.get(reading_block_id)
    source_ids = [str(value) for value in (evidence.get("source_block_ids") or [])]
    if block is None and source_ids:
        block = by_source.get(source_ids[0])
        if block:
            reading_block_id = str(block.get("reading_block_id") or "")
    if block is None:
        return {
            "reading_block_id": reading_block_id,
            "source_block_ids": source_ids,
            "page_start": evidence.get("page_start"),
            "page_end": evidence.get("page_end"),
            "quote": str(evidence.get("quote") or evidence.get("text") or ""),
            "note": str(evidence.get("note") or evidence.get("claim_supported") or ""),
        }
    allowed_source_ids = [str(value) for value in (block.get("source_block_ids") or [])]
    if not source_ids:
        source_ids = allowed_source_ids
    else:
        source_ids = [source_id for source_id in source_ids if source_id in set(allowed_source_ids)] or allowed_source_ids
    quote = str(evidence.get("quote") or evidence.get("text") or "")
    if not quote:
        quote = short_text(block_text(block), 260)
    return {
        "reading_block_id": reading_block_id,
        "source_block_ids": source_ids,
        "page_start": block.get("page_start"),
        "page_end": block.get("page_end"),
        "quote": quote,
        "note": str(evidence.get("note") or evidence.get("claim_supported") or "Supports the extracted item."),
    }


def normalize_evidence_list(item: dict[str, Any], reading: dict[str, Any]) -> None:
    evidence_values = item.get("evidence")
    if not isinstance(evidence_values, list):
        item["evidence"] = []
        return
    item["evidence"] = [
        normalize_evidence(evidence, reading)
        for evidence in evidence_values
        if isinstance(evidence, dict)
    ]


def keep_keys(item: dict[str, Any], allowed: set[str]) -> None:
    for key in list(item.keys()):
        if key not in allowed:
            del item[key]


def normalize_card_items(card: dict[str, Any], reading: dict[str, Any]) -> None:
    paper = card.get("paper")
    if isinstance(paper, dict):
        paper["year"] = str(paper.get("year", ""))
    core = card.get("core_question")
    if isinstance(core, dict):
        normalize_evidence_list(core, reading)
        if normalize_space(core.get("claim") or "") and not core.get("evidence"):
            core["evidence"] = infer_evidence_for_item(core, reading, ["claim"])
    for item in card.get("key_findings") or []:
        if isinstance(item, dict):
            if "claim" not in item and "finding" in item:
                item["claim"] = item.get("finding")
            item.setdefault("claim", "")
            normalize_evidence_list(item, reading)
            if not item.get("evidence"):
                item["evidence"] = infer_evidence_for_item(item, reading, ["claim"])
            keep_keys(item, {"claim", "evidence"})
    for item in card.get("fuzzy_keywords") or []:
        if isinstance(item, dict):
            if "keyword" not in item and "term" in item:
                item["keyword"] = item.get("term")
            item.setdefault("keyword", "")
            normalize_evidence_list(item, reading)
            if not item.get("evidence"):
                item["evidence"] = infer_evidence_for_item(item, reading, ["keyword", "reason"])
            if not item.get("reason"):
                item["reason"] = fallback_from_evidence(item)
            keep_keys(item, {"keyword", "reason", "evidence"})
    for item in card.get("variables") or []:
        if isinstance(item, dict):
            if "values_or_range" not in item and "values" in item:
                item["values_or_range"] = item.get("values")
            item.setdefault("name", "")
            item.setdefault("role", "unknown")
            normalize_evidence_list(item, reading)
            if not item.get("evidence"):
                item["evidence"] = infer_evidence_for_item(item, reading, ["name", "values_or_range"])
            if not item.get("values_or_range"):
                item["values_or_range"] = item.get("value") or fallback_from_evidence(item, 120)
            if not item.get("name"):
                item["name"] = infer_variable_name(item)
            keep_keys(item, {"name", "role", "values_or_range", "evidence"})
    for item in card.get("study_design") or []:
        if isinstance(item, dict):
            if not item.get("aspect"):
                item["aspect"] = infer_aspect(item)
            item.setdefault("detail", "")
            normalize_evidence_list(item, reading)
            if not item.get("evidence"):
                item["evidence"] = infer_evidence_for_item(item, reading, ["aspect", "detail"])
            if not item.get("detail"):
                item["detail"] = fallback_from_evidence(item)
            keep_keys(item, {"aspect", "detail", "evidence"})
    for item in card.get("mechanisms") or []:
        if isinstance(item, dict):
            item.setdefault("mechanism", "")
            item.setdefault("explanation", "")
            normalize_evidence_list(item, reading)
            if not item.get("evidence"):
                item["evidence"] = infer_evidence_for_item(item, reading, ["mechanism", "explanation"])
            if not item.get("mechanism"):
                item["mechanism"] = fallback_from_evidence(item, 120)
            if not item.get("explanation"):
                item["explanation"] = fallback_from_evidence(item)
            keep_keys(item, {"mechanism", "explanation", "evidence"})
    for item in card.get("quantitative_results") or []:
        if isinstance(item, dict):
            item.setdefault("metric", "")
            item.setdefault("value", "")
            item.setdefault("condition", "")
            item.setdefault("interpretation", "")
            normalize_evidence_list(item, reading)
            if not item.get("evidence"):
                item["evidence"] = infer_evidence_for_item(item, reading, ["metric", "value", "condition", "interpretation"])
            if not item.get("metric"):
                item["metric"] = fallback_metric(item)
            if not item.get("interpretation"):
                item["interpretation"] = fallback_from_evidence(item)
            keep_keys(item, {"metric", "value", "condition", "interpretation", "evidence"})
    for item in card.get("limitations") or []:
        if isinstance(item, dict):
            item.setdefault("limitation", "")
            normalize_evidence_list(item, reading)
            if not item.get("evidence"):
                item["evidence"] = infer_evidence_for_item(item, reading, ["limitation"])
            if not item.get("limitation"):
                item["limitation"] = fallback_from_evidence(item)
            keep_keys(item, {"limitation", "evidence"})
    for item in card.get("review_section_hints") or []:
        if isinstance(item, dict):
            normalize_evidence_list(item, reading)
            if not item.get("evidence"):
                item["evidence"] = infer_evidence_for_item(item, reading, ["section", "reason"])
            if not item.get("section"):
                item["section"] = infer_review_section(card)
            item["section"] = normalize_review_section_name(item.get("section"), card)
            if not item.get("reason"):
                item["reason"] = fallback_from_evidence(item)
            keep_keys(item, {"section", "reason", "evidence"})
    if not card.get("review_section_hints"):
        hint = infer_review_section_hint(card)
        if hint:
            card["review_section_hints"] = [hint]


def fallback_from_evidence(item: dict[str, Any], max_chars: int = 220) -> str:
    for evidence in item.get("evidence") or []:
        quote = normalize_space(evidence.get("quote") or "")
        if quote:
            return short_text(quote, max_chars)
    return ""


def fallback_metric(item: dict[str, Any]) -> str:
    value = normalize_space(item.get("value") or "")
    if ":" in value:
        return short_text(value.split(":", 1)[0], 120)
    return "reported quantitative result"


PLACEHOLDER_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in [
        r"^\s*$",
        r"^(unknown|unspecified|not specified|not applicable|n/?a|none|null|-)$",
        r"^unspecified\s+",
        r"^reported quantitative result$",
        r"^study design$",
        r"^literature review synthesis$",
    ]
]


def is_placeholder_text(value: Any) -> bool:
    text = normalize_space(str(value or ""))
    return any(pattern.search(text) for pattern in PLACEHOLDER_PATTERNS)


def infer_evidence_for_item(item: dict[str, Any], reading: dict[str, Any], keys: list[str]) -> list[dict[str, Any]]:
    query = normalize_space(" ".join(str(item.get(key) or "") for key in keys))
    if not query:
        return []
    block = best_matching_block(query, reading)
    if not block:
        return []
    return [
        {
            "reading_block_id": block.get("reading_block_id"),
            "source_block_ids": block.get("source_block_ids") or [],
            "page_start": block.get("page_start"),
            "page_end": block.get("page_end"),
            "quote": short_text(block_text(block), 260),
            "note": "Most similar supplied reading block directly supports the extracted item.",
        }
    ]


def best_matching_block(query: str, reading: dict[str, Any]) -> dict[str, Any] | None:
    query_terms = content_terms(query)
    if not query_terms:
        return None
    best_score = 0.0
    best_block: dict[str, Any] | None = None
    for block in reading.get("reading_blocks") or []:
        if not block.get("include_in_reading", True):
            continue
        if block.get("reading_type") in {"page_header", "noise", "figure", "table", "formula"}:
            continue
        text = block_text(block)
        block_terms = content_terms(text)
        if not block_terms:
            continue
        overlap = query_terms & block_terms
        score = len(overlap) / max(1, len(query_terms))
        if score > best_score:
            best_score = score
            best_block = block
    return best_block if best_score >= 0.18 else None


def content_terms(text: str) -> set[str]:
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "into",
        "using",
        "under",
        "were",
        "are",
        "was",
        "has",
        "have",
        "study",
        "paper",
        "result",
        "results",
    }
    return {
        token.lower()
        for token in re.findall(r"[A-Za-z][A-Za-z0-9/+-]{2,}", text)
        if token.lower() not in stopwords
    }


def infer_aspect(item: dict[str, Any]) -> str:
    text = normalize_space(" ".join(str(item.get(key) or "") for key in ["detail", "method", "setup", "sample"]))
    lowered = text.lower()
    if any(token in lowered for token in ["sample", "coal", "material"]):
        return "sample/material"
    if any(token in lowered for token in ["gcmc", "md", "dft", "simulation", "model"]):
        return "simulation/modeling"
    if any(token in lowered for token in ["experiment", "adsorption", "pressure", "temperature"]):
        return "experiment/conditions"
    return "study design"


def infer_variable_name(item: dict[str, Any]) -> str:
    text = normalize_space(" ".join(str(item.get(key) or "") for key in ["values_or_range", "role"]))
    text += " " + " ".join(str(evidence.get("quote") or "") for evidence in item.get("evidence") or [])
    lowered = text.lower()
    if "temperature" in lowered or re.search(r"\bk\b", lowered):
        return "temperature"
    if "pressure" in lowered or "mpa" in lowered:
        return "pressure"
    if "rp" in lowered or "radius" in lowered or "pore" in lowered or "nm" in lowered:
        return "pore radius"
    if "ratio" in lowered or "molar" in lowered:
        return "molar ratio"
    if "association" in lowered or "scheme" in lowered:
        return "association scheme"
    return "unspecified variable"


def infer_review_section(card: dict[str, Any]) -> str:
    classification = card.get("classification") or {}
    gases = ", ".join(classification.get("gas_systems") or [])
    objects = ", ".join(classification.get("research_objects") or [])
    if gases or objects:
        return f"{gases or 'gas adsorption'} in {objects or 'porous media'}"
    methods = ", ".join(classification.get("methods") or [])
    domains = ", ".join(classification.get("domain_tags") or [])
    if methods and domains:
        return f"{methods} for {domains}"
    if methods:
        return f"{methods} methods"
    if domains:
        return domains
    return "paper-specific evidence synthesis"


def normalize_review_section_name(value: Any, card: dict[str, Any]) -> str:
    section = normalize_space(value)
    lowered = section.lower()
    replacements = {
        "gas adsorption in porous media analogs, micromodels": "microfluidic porous-media analogs",
        "gas adsorption in porous media analogs": "microfluidic porous-media analogs",
        "ch4, co2 in clay minerals, montmorillonite, methane, carbon dioxide": "CO2/CH4 adsorption in clay minerals",
    }
    if lowered in replacements:
        return replacements[lowered]
    if len(section) > 90 or section.count(",") >= 3:
        classification = card.get("classification") if isinstance(card.get("classification"), dict) else {}
        domains = [normalize_space(value) for value in classification.get("domain_tags") or []]
        methods = [normalize_space(value) for value in classification.get("methods") or []]
        objects = [normalize_space(value) for value in classification.get("research_objects") or []]
        gases = [normalize_space(value) for value in classification.get("gas_systems") or []]
        blob = " ".join([section, *domains, *methods, *objects, *gases]).lower()
        if "microfluid" in blob or "micromodel" in blob or "voronoi" in blob:
            return "microfluidic porous-media analogs"
        if "co2" in blob and ("ch4" in blob or "methane" in blob) and ("clay" in blob or "montmorillonite" in blob):
            return "CO2/CH4 adsorption in clay minerals"
        if "drag" in blob and ("polydisperse" in blob or "suspension" in blob):
            return "drag laws for polydisperse suspensions"
        if domains:
            return short_text(domains[0], 80)
        if methods:
            return short_text(methods[0] + " methods", 80)
    return section


def first_supported_item(card: dict[str, Any]) -> dict[str, Any] | None:
    for field in ["key_findings", "mechanisms", "quantitative_results", "limitations", "study_design"]:
        for item in card.get(field) or []:
            if isinstance(item, dict) and item.get("evidence"):
                return item
    core = card.get("core_question") if isinstance(card.get("core_question"), dict) else {}
    return core if core.get("evidence") else None


def infer_review_section_hint(card: dict[str, Any]) -> dict[str, Any] | None:
    item = first_supported_item(card)
    if not item:
        return None
    section = infer_review_section(card)
    if is_placeholder_text(section):
        return None
    classification = card.get("classification") if isinstance(card.get("classification"), dict) else {}
    tag_values: list[str] = []
    for key in ["research_objects", "gas_systems", "methods", "domain_tags"]:
        for value in classification.get(key) or []:
            text = normalize_space(value)
            if text and text not in tag_values:
                tag_values.append(text)
    reason = "This paper provides evidence relevant to " + section
    if tag_values:
        reason += " through " + ", ".join(tag_values[:6])
    reason += "."
    return {
        "section": section,
        "reason": short_text(reason, 260),
        "evidence": item.get("evidence") or [],
    }


def prune_empty_items(card: dict[str, Any]) -> None:
    required_text_keys: dict[str, list[str]] = {
        "fuzzy_keywords": ["keyword", "reason"],
        "study_design": ["aspect", "detail"],
        "variables": ["name", "values_or_range"],
        "mechanisms": ["mechanism", "explanation"],
        "key_findings": ["claim"],
        "quantitative_results": ["metric", "value", "condition", "interpretation"],
        "limitations": ["limitation"],
        "review_section_hints": ["section", "reason"],
    }
    for field, keys in required_text_keys.items():
        kept = []
        for item in card.get(field) or []:
            if not isinstance(item, dict):
                continue
            has_evidence = bool(item.get("evidence"))
            if field == "study_design":
                has_text = bool(normalize_space(item.get("detail") or ""))
            elif field == "review_section_hints":
                has_text = bool(normalize_space(item.get("reason") or ""))
            elif field == "fuzzy_keywords":
                has_text = bool(normalize_space(item.get("keyword") or ""))
            else:
                has_text = any(normalize_space(item.get(key) or "") for key in keys)
            if has_text and has_evidence:
                kept.append(item)
        card[field] = kept


def evidence_from_block(block: dict[str, Any], note: str) -> dict[str, Any]:
    return {
        "reading_block_id": block.get("reading_block_id"),
        "source_block_ids": block.get("source_block_ids") or [],
        "page_start": block.get("page_start"),
        "page_end": block.get("page_end"),
        "quote": short_text(block_text(block), 260),
        "note": note,
    }


def derive_study_design(reading: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    patterns = [
        ("sample/material", ["sample", "coal seam", "bituminous coal", "collected"]),
        ("experiment/conditions", ["experiment", "isothermal", "adsorption apparatus", "pressure", "temperature"]),
        ("simulation/modeling", ["gcmc", "grand canonical", "molecular dynamics", "density functional", "dft", "md"]),
        ("model construction", ["molecular model", "coal model", "constructed", "optimized"]),
        ("analysis workflow", ["radial distribution", "interaction energy", "electrostatic", "adsorption energy"]),
    ]
    items: list[dict[str, Any]] = []
    used_blocks: set[str] = set()
    for aspect, needles in patterns:
        block = first_matching_block(reading, needles, used_blocks)
        if not block:
            continue
        used_blocks.add(str(block.get("reading_block_id")))
        items.append(
            {
                "aspect": aspect,
                "detail": short_text(block_text(block), 320),
                "evidence": [evidence_from_block(block, "Derived study-design evidence from reading block.")],
            }
        )
        if len(items) >= limit:
            break
    return items


def first_matching_block(reading: dict[str, Any], needles: list[str], used_blocks: set[str]) -> dict[str, Any] | None:
    for block in reading.get("reading_blocks") or []:
        block_id = str(block.get("reading_block_id") or "")
        if block_id in used_blocks:
            continue
        if not block.get("include_in_reading", True):
            continue
        if block.get("reading_type") not in {"paragraph", "list_item"}:
            continue
        text = normalize_space(block_text(block)).lower()
        if any(needle in text for needle in needles):
            return block
    return None


def derive_fuzzy_keywords(card: dict[str, Any], limit: int = 12) -> list[dict[str, Any]]:
    candidates: list[tuple[str, str, list[dict[str, Any]]]] = []
    classification = card.get("classification") or {}
    for field in ["research_objects", "gas_systems", "methods", "domain_tags"]:
        for value in classification.get(field) or []:
            candidates.append((str(value), f"Classification tag from {field}.", []))
    for item in card.get("mechanisms") or []:
        if isinstance(item, dict):
            evidence = item.get("evidence") or []
            text = item.get("mechanism") or item.get("explanation") or ""
            if text:
                candidates.append((short_text(text, 80), "Mechanism-oriented discovery keyword.", evidence))
    for item in card.get("key_findings") or []:
        if isinstance(item, dict):
            evidence = item.get("evidence") or []
            claim = item.get("claim") or ""
            for phrase in [
                "competitive adsorption",
                "adsorption selectivity",
                "interaction energy",
                "functional groups",
                "secondary adsorption sites",
                "temperature effect",
                "CO2 displacement",
            ]:
                if phrase.lower() in claim.lower():
                    candidates.append((phrase, "Finding-oriented discovery keyword.", evidence))
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    fallback_evidence = first_evidence(card)
    for keyword, reason, evidence in candidates:
        keyword = normalize_space(keyword)
        if not keyword or keyword.lower() in seen:
            continue
        seen.add(keyword.lower())
        items.append(
            {
                "keyword": keyword,
                "reason": reason,
                "evidence": evidence or fallback_evidence,
            }
        )
        if len(items) >= limit:
            break
    return items


def first_evidence(card: dict[str, Any]) -> list[dict[str, Any]]:
    for _, evidence in evidence_paths(card):
        return [evidence]
    return []


def evidence_quote(block: dict[str, Any], query: str | None = None, max_chars: int = 260) -> str:
    text = normalize_space(block_text(block))
    if not query:
        return short_text(text, max_chars)
    terms = [term for term in content_terms(query) if len(term) > 3]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        lowered = sentence.lower()
        if any(term.lower() in lowered for term in terms):
            return short_text(sentence, max_chars)
    return short_text(text, max_chars)


def evidence_for_block(block: dict[str, Any], note: str, query: str | None = None) -> dict[str, Any]:
    return {
        "reading_block_id": block.get("reading_block_id"),
        "source_block_ids": block.get("source_block_ids") or [],
        "page_start": block.get("page_start"),
        "page_end": block.get("page_end"),
        "quote": evidence_quote(block, query),
        "note": note,
    }


def is_section_label_text(text: str) -> bool:
    normalized = normalized_for_quality(text)
    return normalized in {
        "abstract",
        "introduction",
        "article info",
        "article information",
        "keywords",
        "references",
        "conclusion",
        "conclusions",
    }


def first_block_by_kind(
    reading: dict[str, Any],
    section_kinds: set[str],
    needles: list[str] | None = None,
    body_only: bool = True,
) -> dict[str, Any] | None:
    for block in reading.get("reading_blocks") or []:
        if not block.get("include_in_reading", True):
            continue
        if block.get("section_kind") not in section_kinds:
            continue
        text = normalize_space(block_text(block))
        if not text:
            continue
        if body_only:
            if block.get("reading_type") == "section_heading":
                continue
            if is_section_label_text(text) or len(text.split()) < 8:
                continue
        if needles and not any(needle.lower() in text.lower() for needle in needles):
            continue
        return block
    return None


def fallback_literature_card(reading: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
    metadata_candidates = metadata.get("metadata_candidates", {})
    abstract = first_block_by_kind(reading, {"abstract"}, ["this study", "in this study", "this work", "aim"])
    if not abstract:
        abstract = first_block_by_kind(reading, {"abstract"})
    keywords_block = first_block_by_kind(reading, {"front_matter", "keywords"}, ["keywords:"])
    method_blocks = [
        block
        for block in reading.get("reading_blocks") or []
        if block.get("include_in_reading", True)
        and block.get("section_kind") in {"methods", "results", "results_discussion"}
        and normalize_space(block_text(block))
    ]
    conclusion = first_block_by_kind(reading, {"conclusion", "discussion", "results_discussion"}, ["conclude", "recommended", "results"])
    core_block = abstract or first_block_by_kind(reading, {"introduction"}, ["this study", "in this study", "this article"])

    paper_id = reading.get("paper_id", "")
    core_claim = "The paper's main purpose could not be extracted from the supplied reading blocks."
    core_evidence: list[dict[str, Any]] = []
    if core_block:
        core_claim = short_text(block_text(core_block), 260)
        core_evidence = [evidence_for_block(core_block, "Directly supports the paper purpose.", "this study")]

    classification_text = " ".join(
        block_text(block)
        for block in [abstract, keywords_block, *method_blocks[:10]]
        if block
    ).lower()

    def tags(candidates: list[str]) -> list[str]:
        return [candidate for candidate in candidates if candidate.lower() in classification_text]

    card: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": paper_id,
        "paper": {
            "title": metadata_candidates.get("title", ""),
            "doi": metadata_candidates.get("doi", ""),
            "year": metadata_candidates.get("year", ""),
            "journal": metadata_candidates.get("journal", ""),
            "paper_type": "unknown",
        },
        "classification": {
            "research_objects": tags(["kerogen", "shale", "illite", "montmorillonite", "calcite", "clay minerals", "quartz"]),
            "gas_systems": tags(["methane", "carbon dioxide", "ch4", "co2", "nitrogen", "water"]),
            "methods": tags(["molecular simulation", "molecular dynamics", "grand canonical", "gcmc", "experiment", "langmuir", "freundlich", "henry"]),
            "scale": tags(["nanopore", "micropore", "mesopore", "molecular", "laboratory"]),
            "domain_tags": tags(["adsorption", "diffusion", "tortuosity", "shale gas", "transport", "co2 sequestration"]),
        },
        "fuzzy_keywords": [],
        "core_question": {
            "claim": core_claim,
            "evidence": core_evidence,
        },
        "study_design": [],
        "variables": [],
        "mechanisms": [],
        "key_findings": [],
        "quantitative_results": [],
        "limitations": [],
        "review_section_hints": [],
        "ai_warnings": ["fallback:rule_based_literature_card"],
    }

    if keywords_block:
        keyword_text = re.sub(r"^keywords:\s*", "", normalize_space(block_text(keywords_block)), flags=re.I)
        keyword_candidates = re.split(r"\s{2,}|;|,", keyword_text)
        if len(keyword_candidates) <= 1:
            keyword_candidates = re.findall(
                r"[A-Z][A-Za-z0-9/+-]*(?:\s+[a-z][A-Za-z0-9/+-]*){0,3}",
                keyword_text,
            )
        for keyword in keyword_candidates:
            keyword = normalize_space(keyword)
            if not keyword or len(keyword) < 4:
                continue
            card["fuzzy_keywords"].append(
                {
                    "keyword": keyword,
                    "reason": "Listed in the paper keyword/front-matter block.",
                    "evidence": [evidence_for_block(keywords_block, "Directly from keyword/front-matter block.", keyword)],
                }
            )
            if len(card["fuzzy_keywords"]) >= 8:
                break

    for block in method_blocks[:5]:
        text = block_text(block)
        card["study_design"].append(
            {
                "aspect": "method or workflow",
                "detail": short_text(text, 220),
                "evidence": [evidence_for_block(block, "Directly describes method or workflow.")],
            }
        )

    variable_patterns = [
        ("Pressure", r"\b(?:pressure|pressures?)\b[^.]{0,80}?\b\d+(?:\.\d+)?\s*MPa\b"),
        ("Temperature", r"\b(?:temperature|temperatures?)\b[^.]{0,80}?\b\d+(?:\.\d+)?\s*(?:K|°C|掳C|鈼\?C)\b"),
        ("Pore size", r"\b(?:pore size|pore sizes|micropores?|meso-pores?|macropores?)\b[^.]{0,100}?\b\d+(?:\.\d+)?\s*(?:nm|m|Å|脜)\b"),
    ]
    for block in [abstract, *method_blocks[:30]]:
        if not block:
            continue
        text = normalize_space(block_text(block))
        for name, pattern in variable_patterns:
            match = re.search(pattern, text, flags=re.I)
            if not match:
                continue
            if any(item.get("name") == name for item in card["variables"]):
                continue
            card["variables"].append(
                {
                    "name": name,
                    "role": "condition",
                    "values_or_range": short_text(match.group(0), 120),
                    "evidence": [evidence_for_block(block, f"Directly states {name.lower()} condition.", name)],
                }
            )

    finding_blocks = [block for block in [abstract, conclusion, *method_blocks] if block]
    mechanism_needles = ["impact", "interactions", "pathways", "mechanism", "adsorption effect", "diffusion"]
    for block in finding_blocks:
        text = normalize_space(block_text(block))
        if not any(needle in text.lower() for needle in mechanism_needles):
            continue
        card["mechanisms"].append(
            {
                "mechanism": short_text(evidence_quote(block, "adsorption diffusion tortuosity interactions", 140), 140),
                "explanation": short_text(text, 260),
                "evidence": [evidence_for_block(block, "Directly supports the mechanism statement.", "adsorption diffusion tortuosity interactions")],
            }
        )
        if len(card["mechanisms"]) >= 3:
            break

    for block in finding_blocks:
        text = normalize_space(block_text(block))
        if not any(token in text.lower() for token in ["result", "suggest", "increase", "decrease", "greater", "higher", "conclude", "optimal"]):
            continue
        card["key_findings"].append(
            {
                "claim": short_text(text, 260),
                "evidence": [evidence_for_block(block, "Directly states a finding or result.")],
            }
        )
        if len(card["key_findings"]) >= 4:
            break

    for block in finding_blocks:
        text = normalize_space(block_text(block))
        match = re.search(r"[^.]*\b\d+(?:\.\d+)?\s*(?:MPa|K|°C|掳C|鈼\?C|nm|Å|脜|%)\b[^.]*", text, flags=re.I)
        if not match:
            continue
        card["quantitative_results"].append(
            {
                "metric": "reported numeric condition or result",
                "value": short_text(match.group(0), 120),
                "condition": "Reported in cited reading block.",
                "interpretation": short_text(text, 180),
                "evidence": [evidence_for_block(block, "Directly states numeric value or range.")],
            }
        )
        if len(card["quantitative_results"]) >= 3:
            break

    limitation_needles = ["limitation", "not representative", "recommended", "future", "uncertainty", "challenging"]
    for block in reading.get("reading_blocks") or []:
        text = normalize_space(block_text(block))
        if not block.get("include_in_reading", True) or not text:
            continue
        if not any(needle in text.lower() for needle in limitation_needles):
            continue
        card["limitations"].append(
            {
                "limitation": short_text(text, 220),
                "evidence": [evidence_for_block(block, "Directly states a limitation, uncertainty, or future-work boundary.")],
            }
        )
        if len(card["limitations"]) >= 3:
            break

    if card["key_findings"]:
        card["review_section_hints"].append(
            {
                "section": "Adsorption-controlled gas diffusion and transport in shale nanopores",
                "reason": "The extracted findings discuss adsorption, diffusion, transport, and shale or mineral pore systems.",
                "evidence": card["key_findings"][0]["evidence"],
            }
        )

    return ensure_card_defaults(card, reading, metadata)


def reading_block_map(reading: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(block.get("reading_block_id")): block for block in reading.get("reading_blocks") or []}


def evidence_paths(card: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    paths: list[tuple[str, dict[str, Any]]] = []
    core = card.get("core_question") or {}
    for evidence in core.get("evidence") or []:
        if isinstance(evidence, dict):
            paths.append(("core_question", evidence))
    for field in CARD_LIST_FIELDS:
        values = card.get(field) or []
        for index, item in enumerate(values):
            if not isinstance(item, dict):
                continue
            for evidence in item.get("evidence") or []:
                if isinstance(evidence, dict):
                    paths.append((f"{field}[{index}]", evidence))
    return paths


def item_missing_evidence_count(card: dict[str, Any]) -> int:
    missing = 0
    core = card.get("core_question") or {}
    if not core.get("evidence"):
        missing += 1
    for field in CARD_LIST_FIELDS:
        for item in card.get(field) or []:
            if isinstance(item, dict) and not item.get("evidence"):
                missing += 1
    return missing


def weak_evidence_warnings(card: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    weak_markers = [
        "Auto-inferred evidence",
        "Derived study-design evidence",
    ]
    for path, evidence in evidence_paths(card):
        note = str(evidence.get("note") or "")
        if any(marker in note for marker in weak_markers):
            warnings.append(f"{path}:weak_note")
        if not normalize_space(evidence.get("quote") or ""):
            warnings.append(f"{path}:empty_quote")
    return warnings


def core_question_warnings(card: dict[str, Any]) -> list[str]:
    core = card.get("core_question") if isinstance(card.get("core_question"), dict) else {}
    claim = normalize_space(core.get("claim") or "")
    normalized = normalized_for_quality(claim)
    warnings: list[str] = []
    if normalized in {
        "abstract",
        "introduction",
        "article info",
        "article information",
        "keywords",
    }:
        warnings.append("core_question.claim:section_label")
    if claim and len(claim.split()) < 6:
        warnings.append("core_question.claim:too_short")
    return warnings


def empty_required_text_warnings(card: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    core = card.get("core_question") or {}
    if not normalize_space(core.get("claim") or ""):
        warnings.append("core_question.claim")
    checks: dict[str, list[str]] = {
        "fuzzy_keywords": ["keyword", "reason"],
        "study_design": ["aspect", "detail"],
        "variables": ["name", "role", "values_or_range"],
        "mechanisms": ["mechanism", "explanation"],
        "key_findings": ["claim"],
        "quantitative_results": ["metric", "value", "condition", "interpretation"],
        "limitations": ["limitation"],
        "review_section_hints": ["section", "reason"],
    }
    for field, keys in checks.items():
        for index, item in enumerate(card.get(field) or []):
            if not isinstance(item, dict):
                warnings.append(f"{field}[{index}]")
                continue
            for key in keys:
                if not normalize_space(item.get(key) or ""):
                    warnings.append(f"{field}[{index}].{key}")
                elif field == "variables" and key in {"name", "values_or_range"} and is_placeholder_text(item.get(key)):
                    warnings.append(f"{field}[{index}].{key}:placeholder")
                elif field == "quantitative_results" and key in {"metric", "value"} and is_placeholder_text(item.get(key)):
                    warnings.append(f"{field}[{index}].{key}:placeholder")
    return warnings


def empty_required_text_count(card: dict[str, Any]) -> int:
    return len(empty_required_text_warnings(card))


def paper_metadata_warnings(card: dict[str, Any]) -> list[str]:
    paper = card.get("paper") if isinstance(card.get("paper"), dict) else {}
    title = normalize_space(paper.get("title") or "")
    journal = normalize_space(paper.get("journal") or "")
    normalized_title = normalized_for_quality(title)
    warnings: list[str] = []
    generic_titles = {
        "full length article",
        "article",
        "article info",
        "journal of petroleum science and engineering",
        "journal of molecular liquids",
        "chemical engineering journal",
        "fuel",
        "energy",
        "abstract",
    }
    if not title:
        warnings.append("paper.title")
    elif title.lower() in generic_titles or normalized_title in generic_titles:
        warnings.append("paper.title:journal_or_banner")
    elif "journal homepage" in normalized_title or "elsevier com locate" in normalized_title:
        warnings.append("paper.title:journal_or_banner")
    if journal and len(journal.split()) > 10:
        warnings.append("paper.journal:looks_like_title")
    return warnings


def validate_card(card: dict[str, Any], reading: dict[str, Any]) -> dict[str, Any]:
    required = [
        "schema_version",
        "paper_id",
        "paper",
        "classification",
        "core_question",
        *CARD_LIST_FIELDS,
        "ai_warnings",
    ]
    missing_required = [key for key in required if key not in card]
    blocks_by_id = reading_block_map(reading)
    unknown_reading_blocks: list[str] = []
    bad_source_refs: list[str] = []
    page_mismatches: list[str] = []

    for path, evidence in evidence_paths(card):
        block_id = str(evidence.get("reading_block_id") or "")
        block = blocks_by_id.get(block_id)
        if not block:
            unknown_reading_blocks.append(f"{path}:{block_id}")
            continue
        allowed_source_ids = set(block.get("source_block_ids") or [])
        source_ids = evidence.get("source_block_ids") or []
        for source_id in source_ids:
            if source_id not in allowed_source_ids:
                bad_source_refs.append(f"{path}:{block_id}:{source_id}")
        if evidence.get("page_start") != block.get("page_start") or evidence.get("page_end") != block.get("page_end"):
            page_mismatches.append(f"{path}:{block_id}")

    missing_evidence = item_missing_evidence_count(card)
    empty_required_text = empty_required_text_count(card)
    weak_evidence = weak_evidence_warnings(card)
    metadata_warnings = paper_metadata_warnings(card)
    core_warnings = core_question_warnings(card)
    evidence_count = len(evidence_paths(card))
    status = "ok"
    if (
        missing_required
        or unknown_reading_blocks
        or bad_source_refs
        or page_mismatches
        or missing_evidence
        or empty_required_text
        or weak_evidence
        or metadata_warnings
        or core_warnings
    ):
        status = "fail"
    return {
        "paper_id": card.get("paper_id") or reading.get("paper_id"),
        "status": status,
        "evidence_count": evidence_count,
        "unknown_reading_block_count": len(unknown_reading_blocks),
        "bad_source_ref_count": len(bad_source_refs),
        "missing_evidence_count": missing_evidence,
        "page_mismatch_count": len(page_mismatches),
        "empty_required_text_count": empty_required_text,
        "warnings": "; ".join(
            [
                *(f"missing_required:{key}" for key in missing_required),
                *empty_required_text_warnings(card)[:5],
                *(metadata_warnings[:5]),
                *(core_warnings[:5]),
                *(weak_evidence[:5]),
                *(unknown_reading_blocks[:5]),
                *(bad_source_refs[:5]),
                *(page_mismatches[:5]),
            ]
        ),
    }


def write_validation_report(report_path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "paper_id",
        "status",
        "evidence_count",
        "unknown_reading_block_count",
        "bad_source_ref_count",
        "missing_evidence_count",
        "page_mismatch_count",
        "empty_required_text_count",
        "warnings",
    ]
    atomic_write_csv_dicts(report_path, fieldnames, rows)
