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

# elements.json facet sets
_ELEMENT_ANALYSIS_FACETS = {"analysis", "simulation", "measurement"}
_ELEMENT_RESULT_FACETS = {"finding"}


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


def _elements_views(
    paper_dir: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Read elements.json and produce (analyses, results) atom-view lists.

    Returns None when elements.json is absent or contains no occurrences
    (caller falls back to legacy evidence_atoms path).
    """
    el_doc = _read(paper_dir, "elements.json")
    occurrences = el_doc.get("occurrences") or []
    if not occurrences:
        return None

    used = [occ for occ in occurrences if occ.get("role") == "used"]

    analyses: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    counter = 0
    for occ in used:
        facet = occ.get("facet", "")
        if facet in _ELEMENT_ANALYSIS_FACETS or facet in _ELEMENT_RESULT_FACETS:
            atom = {
                "evidence_atom_id": f"EL-{counter:04d}",
                "atom_type": facet,
                "minimal_claim": occ.get("surface", ""),
                "quote": occ.get("quote", ""),
                "reading_block_id": occ.get("reading_block_id"),
                "confidence": "",
            }
            if facet in _ELEMENT_ANALYSIS_FACETS:
                analyses.append(atom)
            else:
                results.append(atom)
            counter += 1

    return analyses, results


def assemble_decomposition(paper_dir: Path) -> dict[str, Any]:
    """Assemble the single-paper decomposition payload from on-disk artifacts.

    Tries elements.json first; if present and non-empty, uses it for analyses/results
    with source="elements". Otherwise falls back to evidence_atoms.json with
    source="legacy". All other payload sections (abstract/intro/glossary/card) are
    unchanged regardless of source.
    """
    card = _read(paper_dir, "literature_card.json")
    reading = _read(paper_dir, "reading_blocks.json")
    syn_doc = _read(paper_dir, "paper_syntheses.json")
    glossary_doc = _read(paper_dir, "glossary.json")

    paper_id = card.get("paper_id") or reading.get("paper_id") or paper_dir.name
    paper = card.get("paper") or {}
    summary = card.get("summary") or {}

    el_result = _elements_views(paper_dir)

    if el_result is not None:
        # elements path
        analyses, results = el_result
        source = "elements"

        # result_relations: prefer existing paper_syntheses; else derive from card main_findings
        syntheses = syn_doc.get("paper_syntheses") or []
        if syntheses:
            relations = [
                {
                    "synthesis_id": syn.get("synthesis_id"),
                    "synthesis_type": syn.get("synthesis_type"),
                    "claim": syn.get("claim", ""),
                    "supporting_evidence_atom_ids": syn.get("supporting_evidence_atom_ids") or [],
                }
                for syn in syntheses
            ]
        else:
            relations = [
                {
                    "synthesis_id": f"MF-{i:02d}",
                    "synthesis_type": "main_finding",
                    "claim": text,
                    "supporting_evidence_atom_ids": [],
                }
                for i, text in enumerate(summary.get("main_findings") or [])
            ]
    else:
        # legacy path
        atoms_doc = _read(paper_dir, "evidence_atoms.json")
        atoms = atoms_doc.get("evidence_atoms") or []
        analyses = [_atom_view(a) for a in atoms if a.get("atom_type") in _ANALYSIS_TYPES]
        results = [_atom_view(a) for a in atoms if a.get("atom_type") in _RESULT_TYPES]
        relations = [
            {
                "synthesis_id": syn.get("synthesis_id"),
                "synthesis_type": syn.get("synthesis_type"),
                "claim": syn.get("claim", ""),
                "supporting_evidence_atom_ids": syn.get("supporting_evidence_atom_ids") or [],
            }
            for syn in syn_doc.get("paper_syntheses") or []
        ]
        source = "legacy"

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
        "source": source,
    }
