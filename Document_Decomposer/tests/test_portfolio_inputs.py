"""Tests for collect_paper_inputs (R9, portfolio elements migration)."""
import json
from pathlib import Path

import pytest

# collect_paper_inputs is in the portfolio script; import it by path.
import importlib.util, sys

_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "portfolio"
    / "build_paper_portfolio.py"
)
_spec = importlib.util.spec_from_file_location("build_paper_portfolio", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

collect_paper_inputs = _mod.collect_paper_inputs
GAS_NAMES = _mod.GAS_NAMES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_elements(paper_dir: Path, occurrences: list) -> None:
    data = {
        "schema_version": "0.1.0",
        "paper_id": paper_dir.name,
        "occurrences": occurrences,
        "dropped": [],
    }
    (paper_dir / "elements.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _card(main_findings: list[str] | None = None, gas_systems: list[str] | None = None) -> dict:
    return {
        "schema_version": "0.2.0",
        "paper": {"title": "Test paper", "doi": "", "year": "2024"},
        "classification": {"gas_systems": gas_systems or []},
        "summary": {"main_findings": main_findings or [], "objective": ""},
    }


# ---------------------------------------------------------------------------
# Test 1: finding + analysis facets map to atoms-equivalent view
# ---------------------------------------------------------------------------

def test_finding_and_analysis_map_to_atoms(tmp_path: Path):
    """finding and analysis facets (role=used) become atoms with correct fields."""
    paper_dir = tmp_path / "S90"
    paper_dir.mkdir()
    _write_elements(paper_dir, [
        {
            "facet": "finding",
            "surface": "water reduces CH4 adsorption",
            "quote": "Water strongly reduces methane adsorption capacity in clay.",
            "reading_block_id": "S90-RB-0001",
            "role": "used",
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": None,
        },
        {
            "facet": "analysis",
            "surface": "CO2 selectivity depends on pore size",
            "quote": "CO2/CH4 selectivity increases with decreasing pore size.",
            "reading_block_id": "S90-RB-0002",
            "role": "used",
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": None,
        },
        {
            "facet": "simulation",
            "surface": "GCMC",
            "quote": "Simulations were performed using GCMC.",
            "reading_block_id": "S90-RB-0003",
            "role": "used",
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": None,
        },
    ])
    card = _card()
    inputs = collect_paper_inputs(paper_dir, card)

    # only finding and analysis become atoms
    assert len(inputs["atoms"]) == 2
    facets = {a["atom_type"] for a in inputs["atoms"]}
    assert facets == {"finding", "analysis"}

    # field mapping
    finding_atom = next(a for a in inputs["atoms"] if a["atom_type"] == "finding")
    assert finding_atom["minimal_claim"] == "water reduces CH4 adsorption"
    assert "Water strongly" in finding_atom["quote"]
    assert finding_atom["topic_tags"] == []

    assert inputs["evidence_atoms_count"] == 2


# ---------------------------------------------------------------------------
# Test 2: gas detection via canonical_id (display_name in slug)
# ---------------------------------------------------------------------------

def test_gas_detection_via_canonical_id(tmp_path: Path):
    """Material occ with canonical_id 'elem:material/methane' is detected as gas."""
    paper_dir = tmp_path / "S91"
    paper_dir.mkdir()
    _write_elements(paper_dir, [
        {
            "facet": "material",
            "surface": "CH4",
            "quote": "Methane adsorption was measured.",
            "reading_block_id": "S91-RB-0001",
            "role": "used",
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": "elem:material/methane",
        },
        {
            "facet": "material",
            "surface": "montmorillonite",
            "quote": "Montmorillonite clay was used.",
            "reading_block_id": "S91-RB-0002",
            "role": "used",
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": "elem:material/montmorillonite",
        },
    ])
    card = _card()
    inputs = collect_paper_inputs(paper_dir, card)

    # methane is a gas; montmorillonite is not
    assert "CH4" in inputs["gas_systems"]
    assert all("montmorillonite" not in g for g in inputs["gas_systems"])


# ---------------------------------------------------------------------------
# Test 3: gas detection via surface string (direct surface match)
# ---------------------------------------------------------------------------

def test_gas_detection_via_surface(tmp_path: Path):
    """Material occ with surface 'carbon dioxide' (lowercase match) is detected."""
    paper_dir = tmp_path / "S92"
    paper_dir.mkdir()
    _write_elements(paper_dir, [
        {
            "facet": "material",
            "surface": "carbon dioxide",
            "quote": "CO2 adsorption was measured.",
            "reading_block_id": "S92-RB-0001",
            "role": "used",
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": None,
        },
    ])
    card = _card()
    inputs = collect_paper_inputs(paper_dir, card)

    assert "carbon dioxide" in inputs["gas_systems"]


# ---------------------------------------------------------------------------
# Test 4: main_findings wrapped as MF-nn synthesis dicts
# ---------------------------------------------------------------------------

def test_main_findings_wrapped_as_syntheses(tmp_path: Path):
    """summary.main_findings become syntheses with synthesis_id MF-00, MF-01, ..."""
    paper_dir = tmp_path / "S93"
    paper_dir.mkdir()
    _write_elements(paper_dir, [])
    card = _card(main_findings=[
        "CO2 sorption enhanced by clay charge.",
        "Methane sorption correlates with surface area.",
    ])
    inputs = collect_paper_inputs(paper_dir, card)

    assert len(inputs["syntheses"]) == 2
    assert inputs["syntheses"][0]["synthesis_id"] == "MF-00"
    assert inputs["syntheses"][0]["synthesis_type"] == "main_finding"
    assert inputs["syntheses"][0]["claim"] == "CO2 sorption enhanced by clay charge."
    assert inputs["syntheses"][1]["synthesis_id"] == "MF-01"
    assert inputs["syntheses_count"] == 2


# ---------------------------------------------------------------------------
# Test 5: missing elements.json → empty structures (not a crash)
# ---------------------------------------------------------------------------

def test_missing_elements_json_returns_empty_structures(tmp_path: Path):
    """When elements.json is absent, atoms and gas_systems are empty; no crash."""
    paper_dir = tmp_path / "S94"
    paper_dir.mkdir()
    # No elements.json written.
    card = _card(main_findings=["Some finding."])
    inputs = collect_paper_inputs(paper_dir, card)

    assert inputs["atoms"] == []
    assert inputs["gas_systems"] == []
    assert inputs["evidence_atoms_count"] == 0
    # syntheses still derive from card
    assert inputs["syntheses_count"] == 1
    assert inputs["syntheses"][0]["claim"] == "Some finding."


# ---------------------------------------------------------------------------
# Test 6: used-only filter (non-used occurrences are excluded)
# ---------------------------------------------------------------------------

def test_used_only_filter_excludes_non_used(tmp_path: Path):
    """Occurrences with role != 'used' must NOT appear in atoms or gas_systems."""
    paper_dir = tmp_path / "S95"
    paper_dir.mkdir()
    _write_elements(paper_dir, [
        {
            "facet": "finding",
            "surface": "ignored finding",
            "quote": "Some finding.",
            "reading_block_id": "S95-RB-0001",
            "role": "mentioned",          # not "used"
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": None,
        },
        {
            "facet": "material",
            "surface": "methane",
            "quote": "Methane was present.",
            "reading_block_id": "S95-RB-0002",
            "role": "background",         # not "used"
            "quote_verified": True,
            "digits_verified": False,
            "values": [],
            "canonical_id": "elem:material/methane",
        },
    ])
    card = _card()
    inputs = collect_paper_inputs(paper_dir, card)

    assert inputs["atoms"] == []
    assert inputs["gas_systems"] == []
    assert inputs["evidence_atoms_count"] == 0
