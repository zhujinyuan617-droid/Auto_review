"""AI extraction of research elements from one paper's reading blocks.

Output: library/<Sxx>/elements.json. Every occurrence carries a verbatim quote
verified against its cited reading block (loose level mandatory); numeric values
are parsed only when the digits-verified level also passes. canonical_id is left
null here — matching/normalization is a separate step (element_matching).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    "6. facet='finding': report ONLY conclusions this paper itself establishes (directional "
    "effects, measured outcomes, demonstrated mechanisms). surface = a short declarative "
    "noun phrase (e.g. 'water reduces methane adsorption capacity'). The quote must contain "
    "the concluding statement verbatim. A review restating another paper's findings -> role='mentioned'.\n"
    "Report the paper's PRINCIPAL findings (the conclusions an abstract would state), "
    "not every results sentence -- prefer statements from abstract/conclusion blocks. "
    "A finding asserts a direction or outcome (X increases/reduces/controls Y); the bare "
    "quantity or activity it concerns (e.g. 'isosteric heat', 'isotherm fitting') belongs "
    "to analysis, not finding. A review's OWN cross-literature synthesis conclusion is "
    "role='used'; an individual result it merely restates from a cited paper is 'mentioned'.\n"
    "7. Output strictly the JSON schema; no Markdown."
)

# ---------------------------------------------------------------------------
# Finding-only system prompt
# Composed from the SAME rule texts as _SYSTEM (rules 1, 2, 3 verbatim;
# the full finding rule (was #6); final strict-output rule), renumbered 1–5.
# Do NOT derive this by parsing _SYSTEM at runtime — write the constant once.
# ---------------------------------------------------------------------------
_FINDING_SYSTEM = (
    "You extract PRINCIPAL FINDINGS from one paper's reading blocks.\n"
    "Rules:\n"
    "1. role='used' ONLY for what THIS paper itself did/measured/simulated/analyzed. "
    "Things only cited from other papers or general background are role='mentioned'. "
    "In a review article almost everything is 'mentioned'.\n"
    "2. For EVERY element give one verbatim quote (<=300 chars) copied EXACTLY, "
    "character-for-character, from ONE reading block, and that block's reading_block_id. "
    "The quote must contain the element mention. For 'condition' elements the quote "
    "must include the numeric phrase. Never paraphrase inside the quote.\n"
    "3. surface = the element name as this paper writes it (short noun phrase).\n"
    "4. facet='finding': report ONLY conclusions this paper itself establishes (directional "
    "effects, measured outcomes, demonstrated mechanisms). surface = a short declarative "
    "noun phrase (e.g. 'water reduces methane adsorption capacity'). The quote must contain "
    "the concluding statement verbatim. A review restating another paper's findings -> role='mentioned'.\n"
    "Report the paper's PRINCIPAL findings (the conclusions an abstract would state), "
    "not every results sentence -- prefer statements from abstract/conclusion blocks. "
    "A finding asserts a direction or outcome (X increases/reduces/controls Y); the bare "
    "quantity or activity it concerns (e.g. 'isosteric heat', 'isotherm fitting') belongs "
    "to analysis, not finding. A review's OWN cross-literature synthesis conclusion is "
    "role='used'; an individual result it merely restates from a cited paper is 'mentioned'.\n"
    "5. Output strictly the JSON schema; no Markdown."
)

# Same JSON shape as ELEMENTS_SCHEMA_HINT; facet will always be 'finding'.
FINDING_SCHEMA_HINT = ELEMENTS_SCHEMA_HINT


def _finding_only_seeds(seeds: dict) -> dict:
    """Return a narrowed seeds dict containing only the 'finding' facet entry."""
    finding_facets = [f for f in seeds["facets"] if f["id"] == "finding"]
    return {"facets": finding_facets, "synonyms": {}}


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


def build_finding_prompt(reading: dict, seeds: dict, max_block_chars: int = MAX_BLOCK_CHARS) -> list[dict]:
    """Narrowed prompt: only extracts 'finding' facet.

    system = rules 1/2/3 + full finding rule + strict-output (renumbered 1..5,
    defined in _FINDING_SYSTEM).  payload facets filtered to id=='finding'.
    """
    finding_seeds = _finding_only_seeds(seeds)
    payload = {
        "paper_id": reading.get("paper_id", ""),
        "facets": [{"id": f["id"], "description": f["description"]} for f in finding_seeds["facets"]],
        "reading_blocks": _blocks_for_prompt(reading, max_block_chars),
    }
    user = (
        "Extract the principal findings from this paper.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    return [{"role": "system", "content": _FINDING_SYSTEM}, {"role": "user", "content": user}]


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


def backfill_findings(paper_dir: Path, client: Any, seeds: dict) -> dict:
    """Idempotent finding backfill for a paper that already has elements.json.

    Reads existing elements.json (raises ValueError if absent), removes all
    occurrences with facet=='finding', calls the AI with _FINDING_SYSTEM using
    a narrowed seeds dict (finding facet only), verifies quotes via
    parse_elements_response, keeps only facet=='finding' results (non-finding
    items returned by AI are dropped as bad_facet), appends them to the
    non-finding occurrences, and writes back.

    New dropped entries carry {"phase": "finding_backfill"} to distinguish them
    from the original extraction phase; original dropped list is preserved.

    Returns {"added": n, "removed_old": m, "dropped": k}.
    """
    elements_path = paper_dir / "elements.json"
    if not elements_path.exists():
        raise ValueError(f"elements.json not found: {elements_path}")

    data: dict = json.loads(elements_path.read_text(encoding="utf-8"))
    reading = json.loads((paper_dir / "reading_blocks.json").read_text(encoding="utf-8"))

    # Strip existing finding occurrences (idempotent: remove before re-adding).
    original_occs: list[dict] = data.get("occurrences") or []
    non_finding = [o for o in original_occs if o.get("facet") != "finding"]
    removed_old = len(original_occs) - len(non_finding)

    # Call AI with the finding-only system prompt.
    finding_seeds = _finding_only_seeds(seeds)
    messages = build_finding_prompt(reading, seeds)
    raw = client.chat_json(messages, FINDING_SCHEMA_HINT)

    # parse_elements_response enforces the facet whitelist: non-finding items
    # from the AI are dropped as bad_facet automatically.
    new_occs, new_dropped = parse_elements_response(raw, reading, finding_seeds)

    # Extra safety: keep only facet=='finding' from what parse returned.
    finding_occs = [o for o in new_occs if o.get("facet") == "finding"]

    # Tag new dropped entries with phase for auditability.
    tagged_dropped = [{**d, "phase": "finding_backfill"} for d in new_dropped]

    data["occurrences"] = non_finding + finding_occs
    data["dropped"] = (data.get("dropped") or []) + tagged_dropped

    write_json(elements_path, data)
    return {"added": len(finding_occs), "removed_old": removed_old, "dropped": len(new_dropped)}
