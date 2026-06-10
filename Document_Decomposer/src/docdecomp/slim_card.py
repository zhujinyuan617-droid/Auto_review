"""Slim index card builder (architecture v2, see CONNECTION_PLAN.md).

The card is no longer a thick, claim-bearing summary. It holds only what the
connection layer needs:
  - paper      : metadata (title/doi/year/journal/paper_type)
  - classification : coarse tags (research_objects / methods / domain_tags / ...)
  - summary    : a FIXED-FORMAT coarse summary, NON-FACT, for linking only
                 (objective + direction-level main_findings + methods_systems)

Hard design rules (mirror the architecture):
  - No verbatim quotes, no evidence objects, no precise numbers in the card.
    Facts live in the reading blocks; the card is only for navigation/linking.
  - main_findings state DIRECTION (what raises/lowers/affects what), not values.

This module reuses the block-serialization helpers from literature_card.py but
defines its own slim prompt / validation, leaving the old thick-card code untouched.
"""

from __future__ import annotations

import json
from typing import Any

from docdecomp.literature_card import (
    is_journal_or_banner_title,
    normalize_space,
    reading_block_prompt_item,
    relevant_reading_blocks,
)

SLIM_SCHEMA_VERSION = "0.3.0"

# Focused reading: feed only substantive sections to the card builder, so the summary is
# distilled from a short, relevant context (not 140 truncated blocks incl. references).
# This is the single "long read" in the pipeline; keeping it focused is what makes the
# summary directionally reliable enough for downstream steps to trust without re-reading.
SUBSTANTIVE_KINDS = {
    "abstract", "introduction", "methods", "results",
    "results_discussion", "discussion", "conclusion",
}

SLIM_SCHEMA_HINT = (
    "Return only one JSON object with keys: schema_version, paper_id, paper, "
    "classification, summary, ai_warnings. Do not wrap in Markdown. No evidence "
    "objects, no quotes, no per-item citations anywhere."
)


def build_slim_prompt(reading: dict, metadata: dict, max_block_chars: int = 900) -> list[dict]:
    paper_id = reading["paper_id"]
    mc = metadata.get("metadata_candidates", {})
    focused = [b for b in relevant_reading_blocks(reading) if b.get("section_kind") in SUBSTANTIVE_KINDS]
    if not focused:  # Docling didn't label sections -> fall back to all relevant blocks
        focused = relevant_reading_blocks(reading)
    blocks = [reading_block_prompt_item(b, max_block_chars) for b in focused]
    payload = {
        "paper_id": paper_id,
        "metadata_candidates": {
            "title": mc.get("title", ""), "doi": mc.get("doi", ""),
            "year": mc.get("year", ""), "journal": mc.get("journal", ""),
        },
        "allowed_paper_types": ["experimental", "simulation", "review", "hybrid", "other", "unknown"],
        "reading_blocks": blocks,
    }
    system = (
        "You build a SLIM index card from a paper's reading blocks. Its only purpose is "
        "cross-paper linking, NOT to record facts. Use only the supplied blocks. "
        "Never invent. Return strict JSON only."
    )
    user = (
        "Build one slim index card (schema_version 0.3.0). Output exactly these keys: "
        "schema_version, paper_id, paper, classification, summary, ai_warnings.\n"
        "- paper: {title, doi, year, journal, paper_type}. Use metadata_candidates as hints; "
        "if its title is empty or is a journal/banner name, infer the real title from front-matter "
        "blocks. paper_type is one of the allowed types.\n"
        "- classification: {domain_tags}: an array of SHORT normalized topic tags for the whole "
        "paper (3-6 tags). Tags MUST cover the paper's core MECHANISM or PHENOMENON words from "
        "the title/conclusions (e.g. adsorption, diffusion, confinement, phase behavior, gas "
        "transport) -- never only reservoir/scenario types (e.g. 'shale gas', 'unconventional "
        "reservoirs'). A reader filtering by mechanism must find this paper. research_objects "
        "and methods are filled by the system from extracted elements -- do NOT output them.\n"
        "- summary: {objective, main_findings, methods_systems}. This is a COARSE, DIRECTION-LEVEL "
        "summary for linking only:\n"
        "    objective    : one sentence, the research question/purpose.\n"
        "    main_findings: 2 to 6 SHORT statements, each stating a DIRECTION or relationship "
        "(what increases / decreases / affects / determines what). DO NOT include precise numbers, "
        "units, or thresholds -- those stay in the source. Example: 'higher water content -> lower "
        "methane adsorption'.\n"
        "    methods_systems: one short line naming the methods and the system studied.\n"
        "- Do NOT add quotes, evidence, page numbers, or citations anywhere. Do NOT assert precise "
        "numeric facts. If the paper is not in English, still fill what you can but note it in ai_warnings.\n"
        "Here is the input JSON:\n" + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_slim_repair_prompt(previous_messages: list[dict], candidate: dict, validation: dict) -> list[dict]:
    instr = (
        "The previous slim card failed validation. Return a corrected complete slim card JSON "
        "(keys: schema_version, paper_id, paper, classification, summary, ai_warnings). "
        "Fix exactly these problems and add nothing else:\n" + json.dumps(validation, ensure_ascii=False)
    )
    return [*previous_messages,
            {"role": "assistant", "content": json.dumps(candidate, ensure_ascii=False)},
            {"role": "user", "content": instr}]


def ensure_slim_defaults(card: dict, reading: dict, metadata: dict) -> dict:
    mc = metadata.get("metadata_candidates", {})
    card.setdefault("schema_version", SLIM_SCHEMA_VERSION)
    card["schema_version"] = SLIM_SCHEMA_VERSION
    card.setdefault("paper_id", reading.get("paper_id", ""))

    paper = card.get("paper") if isinstance(card.get("paper"), dict) else {}
    paper.setdefault("title", mc.get("title", ""))
    paper.setdefault("doi", mc.get("doi", ""))
    paper.setdefault("year", mc.get("year", ""))
    paper.setdefault("journal", mc.get("journal", ""))
    paper.setdefault("paper_type", "unknown")
    # backfill metadata when the model left it blank or used a banner/journal as title
    mt = normalize_space(mc.get("title") or "")
    if mt and (not normalize_space(paper.get("title") or "") or is_journal_or_banner_title(paper.get("title") or "")):
        paper["title"] = mt
    for k in ("doi", "year", "journal"):
        if normalize_space(mc.get(k) or ""):
            paper[k] = normalize_space(mc.get(k))
    card["paper"] = paper

    raw_cls = card.get("classification") if isinstance(card.get("classification"), dict) else {}
    cls: dict = {}
    for k in ("research_objects", "methods", "domain_tags", "topic_ids"):
        v = raw_cls.get(k)
        cls[k] = [normalize_space(x) for x in v if normalize_space(x)] if isinstance(v, list) else []
    card["classification"] = cls

    summ = card.get("summary") if isinstance(card.get("summary"), dict) else {}
    summ.setdefault("objective", "")
    mf = summ.get("main_findings")
    summ["main_findings"] = [normalize_space(x) for x in mf if normalize_space(x)] if isinstance(mf, list) else []
    summ.setdefault("methods_systems", "")
    card["summary"] = summ

    if not isinstance(card.get("ai_warnings"), list):
        card["ai_warnings"] = []
    return card


def validate_slim_card(card: dict) -> dict:
    warnings: list[str] = []
    cls = card.get("classification") or {}
    if not cls.get("domain_tags"):
        warnings.append("classification_empty")
    summ = card.get("summary") or {}
    if not normalize_space(summ.get("objective") or ""):
        warnings.append("summary_objective_empty")
    if not (summ.get("main_findings") or []):
        warnings.append("summary_main_findings_empty")
    if not normalize_space((card.get("paper") or {}).get("title") or ""):
        warnings.append("title_empty")
    return {"status": "ok" if not warnings else "needs_fix", "warnings": warnings,
            "n_tags": len(cls.get("domain_tags") or []),
            "n_findings": len(summ.get("main_findings") or [])}


def fallback_slim_card(reading: dict, metadata: dict) -> dict:
    """Metadata-only card; will fail validation (no summary) so it is written as a
    failed candidate rather than silently passing."""
    card = {"paper_id": reading.get("paper_id", ""), "ai_warnings": ["fallback: model did not return a usable slim card"]}
    return ensure_slim_defaults(card, reading, metadata)
