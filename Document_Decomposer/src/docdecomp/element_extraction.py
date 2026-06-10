"""AI extraction of research elements from one paper's reading blocks.

Output: library/<Sxx>/elements.json. Every occurrence carries a verbatim quote
verified against its cited reading block (loose level mandatory); numeric values
are parsed only when the digits-verified level also passes. canonical_id is left
null here — matching/normalization is a separate step (element_matching).
"""
from __future__ import annotations

import json
from pathlib import Path

from .element_quotes import verify_quote
from .element_values import parse_values
from .io_utils import write_json

SCHEMA_VERSION = "0.1.0"
MAX_BLOCK_CHARS = 700
MAX_QUOTE_CHARS = 300

ELEMENTS_SCHEMA_HINT = (
    'Return only one JSON object: {"paper_id": str, "elements": [{"facet": str, '
    '"surface": str, "quote": str, "reading_block_id": str, "role": "used"|"mentioned", '
    '"proposed_facet": str (optional)}]}. Do not wrap the JSON in Markdown.'
)

_SYSTEM = (
    "You extract RESEARCH ELEMENTS from one paper's reading blocks: every concrete "
    "technique, method, material and condition the paper involves.\n"
    "Rules:\n"
    "1. role='used' ONLY for what THIS paper itself did/measured/simulated/analyzed. "
    "Things only cited from other papers or general background are role='mentioned'. "
    "In a review article almost everything is 'mentioned'.\n"
    "2. For EVERY element give one verbatim quote (<=300 chars) copied EXACTLY, "
    "character-for-character, from ONE reading block, and that block's reading_block_id. "
    "The quote must contain the element mention. For 'condition' elements the quote "
    "must include the numeric phrase. Never paraphrase inside the quote.\n"
    "3. surface = the element name as this paper writes it (short noun phrase).\n"
    "4. facet must be one of the listed facet ids. If none fits, use facet='other' "
    "and set proposed_facet to a short English category name.\n"
    "5. Be exhaustive on methods/characterization/simulation/conditions; list each "
    "distinct element once per role (pick its clearest quote).\n"
    "6. Output strictly the JSON schema; no Markdown."
)


def _blocks_for_prompt(reading: dict, max_block_chars: int) -> list[dict]:
    out = []
    for b in reading.get("reading_blocks") or []:
        if not isinstance(b, dict) or not b.get("reading_block_id"):
            continue
        if not b.get("include_in_reading", True):
            continue
        text = (b.get("text") or b.get("caption") or "").strip()
        if not text:
            continue
        out.append(
            {
                "reading_block_id": b["reading_block_id"],
                "section_kind": b.get("section_kind", ""),
                "text": text[:max_block_chars],
            }
        )
    return out


def build_elements_prompt(reading: dict, seeds: dict, max_block_chars: int = MAX_BLOCK_CHARS) -> list[dict]:
    payload = {
        "paper_id": reading.get("paper_id", ""),
        "facets": [{"id": f["id"], "description": f["description"]} for f in seeds["facets"]],
        "reading_blocks": _blocks_for_prompt(reading, max_block_chars),
    }
    user = (
        "Extract all research elements from this paper.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def parse_elements_response(raw: dict, reading: dict, seeds: dict) -> tuple[list[dict], list[dict]]:
    facet_ids = {f["id"] for f in seeds["facets"]}
    block_text = {
        b["reading_block_id"]: (b.get("text") or b.get("caption") or "")
        for b in reading.get("reading_blocks") or []
        if isinstance(b, dict) and b.get("reading_block_id")
    }
    occurrences: list[dict] = []
    dropped: list[dict] = []
    elements = raw.get("elements")
    if not isinstance(elements, list):
        elements = []
    for item in elements:
        if not isinstance(item, dict):
            dropped.append({"surface": "", "reason": "bad_item"})
            continue
        surface = str(item.get("surface") or "").strip()
        facet = str(item.get("facet") or "").strip()
        quote = str(item.get("quote") or "").strip()[:MAX_QUOTE_CHARS]
        rb_id = str(item.get("reading_block_id") or "").strip()
        role = str(item.get("role") or "").strip()
        if facet == "other" and item.get("proposed_facet"):
            facet = "proposed:" + str(item["proposed_facet"]).strip()
        elif facet not in facet_ids:
            dropped.append({"surface": surface, "reason": "bad_facet"})
            continue
        if role not in ("used", "mentioned"):
            dropped.append({"surface": surface, "reason": "bad_role"})
            continue
        if rb_id not in block_text:
            dropped.append({"surface": surface, "reason": "unknown_block"})
            continue
        check = verify_quote(quote, block_text[rb_id])
        if not check["quote_verified"]:
            dropped.append({"surface": surface, "reason": "quote_not_found" if check["reason"] == "not_found" else check["reason"]})
            continue
        values = parse_values(quote) if facet == "condition" and check["digits_verified"] else []
        # Deliberate: no (facet, surface, role) dedup — the prompt asks for distinct
        # elements, but repeats are tolerated; index-level stats count DISTINCT papers.
        occurrences.append(
            {
                "facet": facet,
                "surface": surface,
                "quote": quote,
                "reading_block_id": rb_id,
                "role": role,
                "quote_verified": True,
                "digits_verified": check["digits_verified"],
                "values": values,
                "canonical_id": None,
            }
        )
    return occurrences, dropped


def run_element_extraction(paper_dir: Path, client, seeds: dict) -> dict:
    reading = json.loads((paper_dir / "reading_blocks.json").read_text(encoding="utf-8"))
    messages = build_elements_prompt(reading, seeds)
    raw = client.chat_json(messages, ELEMENTS_SCHEMA_HINT)
    occurrences, dropped = parse_elements_response(raw, reading, seeds)
    result = {
        "schema_version": SCHEMA_VERSION,
        "paper_id": reading.get("paper_id", paper_dir.name),
        "occurrences": occurrences,
        "dropped": dropped,
    }
    write_json(paper_dir / "elements.json", result)
    return result
