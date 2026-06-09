from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# The decomposition reader shows the "analysis -> result -> relation" spine.
# Atom types background/limitation/scope/other are intentionally NOT surfaced
# here (they are not part of that spine); a future task may add a dedicated
# limitations section if needed.
_ANALYSIS_TYPES = {"method", "variable", "mechanism"}
_RESULT_TYPES = {"result", "quantitative_result"}


def _read(paper_dir: Path, name: str) -> dict[str, Any]:
    path = paper_dir / name
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _blocks_of_kind(reading: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    out = []
    for block in reading.get("reading_blocks") or []:
        if block.get("section_kind") == kind:
            out.append({"reading_block_id": block.get("reading_block_id"), "text": block.get("text", "")})
    return out


def _atom_view(atom: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_atom_id": atom.get("evidence_atom_id"),
        "atom_type": atom.get("atom_type"),
        "minimal_claim": atom.get("minimal_claim", ""),
        "quote": atom.get("quote", ""),
        "reading_block_id": atom.get("reading_block_id"),
        "confidence": atom.get("confidence"),
    }


def assemble_decomposition(paper_dir: Path) -> dict[str, Any]:
    """Assemble the single-paper decomposition payload from on-disk artifacts.

    Each artifact is optional; missing ones degrade to empty sections. Atoms carry
    a reading_block_id source anchor; syntheses trace via supporting atom ids.
    """
    card = _read(paper_dir, "literature_card.json")
    reading = _read(paper_dir, "reading_blocks.json")
    atoms_doc = _read(paper_dir, "evidence_atoms.json")
    syn_doc = _read(paper_dir, "paper_syntheses.json")
    glossary_doc = _read(paper_dir, "glossary.json")

    paper_id = card.get("paper_id") or reading.get("paper_id") or paper_dir.name
    paper = card.get("paper") or {}
    summary = card.get("summary") or {}

    atoms = atoms_doc.get("evidence_atoms") or []
    analyses = [_atom_view(a) for a in atoms if a.get("atom_type") in _ANALYSIS_TYPES]
    results = [_atom_view(a) for a in atoms if a.get("atom_type") in _RESULT_TYPES]

    relations = []
    for syn in syn_doc.get("paper_syntheses") or []:
        relations.append({
            "synthesis_id": syn.get("synthesis_id"),
            "synthesis_type": syn.get("synthesis_type"),
            "claim": syn.get("claim", ""),
            "supporting_evidence_atom_ids": syn.get("supporting_evidence_atom_ids") or [],
        })

    return {
        "paper_id": paper_id,
        "card": {
            "title": paper.get("title", ""),
            "year": str(paper.get("year", "")),
            "journal": paper.get("journal", ""),
            "objective": summary.get("objective", ""),
            "main_findings": summary.get("main_findings") or [],
        },
        "abstract_blocks": _blocks_of_kind(reading, "abstract"),
        "intro_blocks": _blocks_of_kind(reading, "introduction"),
        "glossary": glossary_doc.get("glossary") or [],
        "analyses": analyses,
        "results": results,
        "result_relations": relations,
    }
