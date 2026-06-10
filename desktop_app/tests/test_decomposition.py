from pathlib import Path

from _library_fixtures import (
    write_card,
    write_elements,
    write_evidence_atoms,
    write_glossary,
    write_paper_syntheses,
    write_reading_blocks,
)

from autoreview_app.decomposition import assemble_decomposition


def _full_paper(library: Path) -> Path:
    pid = "S1"
    write_card(library, pid, title="Methane Study", doi="10.1/a", findings=["Adsorption rises."])
    write_reading_blocks(library, pid, [
        {"reading_block_id": "S1-RB-0001", "section_kind": "abstract", "text": "We study methane."},
        {"reading_block_id": "S1-RB-0002", "section_kind": "introduction", "text": "The problem is X."},
        {"reading_block_id": "S1-RB-0003", "section_kind": "methods", "text": "We used GCMC."},
    ])
    write_evidence_atoms(library, pid, [
        {"evidence_atom_id": "S1-EVATOM-0001", "atom_type": "method", "minimal_claim": "GCMC simulation", "quote": "We used GCMC.", "reading_block_id": "S1-RB-0003", "confidence": "high"},
        {"evidence_atom_id": "S1-EVATOM-0002", "atom_type": "result", "minimal_claim": "Adsorption rises", "quote": "rises", "reading_block_id": "S1-RB-0003", "confidence": "medium"},
        {"evidence_atom_id": "S1-EVATOM-0003", "atom_type": "quantitative_result", "minimal_claim": "12 mmol/g", "quote": "12", "reading_block_id": "S1-RB-0003", "confidence": "high"},
        {"evidence_atom_id": "S1-EVATOM-0004", "atom_type": "background", "minimal_claim": "context", "quote": "x", "reading_block_id": "S1-RB-0002", "confidence": "low"},
    ])
    write_paper_syntheses(library, pid, [
        {"synthesis_id": "S1-SYN-0001", "synthesis_type": "method_result_link", "claim": "GCMC shows adsorption rises", "supporting_evidence_atom_ids": ["S1-EVATOM-0001", "S1-EVATOM-0002"]},
    ])
    write_glossary(library, pid, [
        {"term": "GCMC", "definition": "Grand Canonical Monte Carlo", "reading_block_id": "S1-RB-0003"},
    ])
    return library / pid


def test_assembles_all_sections(tmp_path: Path):
    paper_dir = _full_paper(tmp_path / "library")
    view = assemble_decomposition(paper_dir)

    assert view["paper_id"] == "S1"
    assert view["card"]["title"] == "Methane Study"
    assert [b["text"] for b in view["abstract_blocks"]] == ["We study methane."]
    assert [b["reading_block_id"] for b in view["intro_blocks"]] == ["S1-RB-0002"]
    assert view["glossary"][0]["term"] == "GCMC"

    assert {a["evidence_atom_id"] for a in view["analyses"]} == {"S1-EVATOM-0001"}
    assert {a["evidence_atom_id"] for a in view["results"]} == {"S1-EVATOM-0002", "S1-EVATOM-0003"}
    assert all("reading_block_id" in a for a in view["analyses"] + view["results"])
    # the background atom is surfaced in neither analyses nor results
    shown = {a["evidence_atom_id"] for a in view["analyses"] + view["results"]}
    assert "S1-EVATOM-0004" not in shown

    assert view["result_relations"][0]["synthesis_id"] == "S1-SYN-0001"
    assert view["result_relations"][0]["supporting_evidence_atom_ids"] == ["S1-EVATOM-0001", "S1-EVATOM-0002"]


def test_missing_fine_layer_degrades_gracefully(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S9", title="Bare", doi="")
    view = assemble_decomposition(library / "S9")

    assert view["paper_id"] == "S9"
    assert view["card"]["title"] == "Bare"
    assert view["abstract_blocks"] == []
    assert view["intro_blocks"] == []
    assert view["glossary"] == []
    assert view["analyses"] == []
    assert view["results"] == []
    assert view["result_relations"] == []


def test_paper_id_falls_back_to_dirname(tmp_path: Path):
    library = tmp_path / "library"
    (library / "S7").mkdir(parents=True)
    view = assemble_decomposition(library / "S7")
    assert view["paper_id"] == "S7"


# ---------------------------------------------------------------------------
# R5: elements source path
# ---------------------------------------------------------------------------

_LEGACY_PAYLOAD_KEYS = {
    "paper_id", "card", "abstract_blocks", "intro_blocks",
    "glossary", "analyses", "results", "result_relations",
}


def _elements_paper(library: Path) -> Path:
    """Minimal paper with elements.json + v3 card with main_findings."""
    pid = "E1"
    write_card(library, pid, title="Elements Study", doi="10.2/b",
               findings=["Finding alpha.", "Finding beta."])
    write_reading_blocks(library, pid, [
        {"reading_block_id": "E1-RB-0001", "section_kind": "abstract", "text": "Abstract text."},
    ])
    write_elements(library, pid, [
        # analysis facet, used → included in analyses
        {"facet": "analysis", "surface": "regression analysis",
         "quote": "We used regression.", "reading_block_id": "E1-RB-0001", "role": "used"},
        # simulation facet, used → included in analyses
        {"facet": "simulation", "surface": "MD simulation",
         "quote": "MD was run.", "reading_block_id": "E1-RB-0001", "role": "used"},
        # finding facet, used → included in results
        {"facet": "finding", "surface": "Temperature rises.",
         "quote": "T increases.", "reading_block_id": "E1-RB-0001", "role": "used"},
        # finding facet, mentioned → EXCLUDED (role != "used")
        {"facet": "finding", "surface": "Excluded finding.",
         "quote": "not included.", "reading_block_id": "E1-RB-0001", "role": "mentioned"},
        # material facet, used → EXCLUDED (facet not in target sets)
        {"facet": "material", "surface": "silica",
         "quote": "silica used.", "reading_block_id": "E1-RB-0001", "role": "used"},
    ])
    write_glossary(library, pid, [
        {"term": "MD", "definition": "Molecular Dynamics", "reading_block_id": "E1-RB-0001"},
    ])
    return library / pid


def test_elements_source_analyses_and_results(tmp_path: Path):
    """elements.json drives analyses/results when present; source=='elements'."""
    paper_dir = _elements_paper(tmp_path / "library")
    view = assemble_decomposition(paper_dir)

    assert view["source"] == "elements"

    # analyses: facets analysis + simulation, role==used → 2 items
    assert len(view["analyses"]) == 2
    facets = {a["atom_type"] for a in view["analyses"]}
    assert facets == {"analysis", "simulation"}

    # results: facet finding, role==used → 1 item (mentioned excluded)
    assert len(view["results"]) == 1
    assert view["results"][0]["atom_type"] == "finding"
    assert view["results"][0]["minimal_claim"] == "Temperature rises."
    assert view["results"][0]["quote"] == "T increases."

    # atom_view keys must be present in every atom
    required_atom_keys = {
        "evidence_atom_id", "atom_type", "minimal_claim",
        "quote", "reading_block_id", "confidence",
    }
    for a in view["analyses"] + view["results"]:
        assert required_atom_keys.issubset(a.keys()), f"Missing keys in {a}"

    # evidence_atom_id pattern: EL-NNNN
    import re
    for a in view["analyses"] + view["results"]:
        assert re.match(r"^EL-\d{4}$", a["evidence_atom_id"]), a["evidence_atom_id"]


def test_elements_source_result_relations_from_main_findings(tmp_path: Path):
    """When no paper_syntheses.json, result_relations come from card main_findings."""
    paper_dir = _elements_paper(tmp_path / "library")
    view = assemble_decomposition(paper_dir)

    rels = view["result_relations"]
    assert len(rels) == 2  # card has ["Finding alpha.", "Finding beta."]
    assert rels[0]["synthesis_id"] == "MF-00"
    assert rels[1]["synthesis_id"] == "MF-01"
    assert rels[0]["synthesis_type"] == "main_finding"
    assert rels[0]["claim"] == "Finding alpha."
    assert rels[0]["supporting_evidence_atom_ids"] == []


def test_elements_source_relations_prefer_syntheses(tmp_path: Path):
    """If paper_syntheses.json exists, use legacy relations even under elements path."""
    library = tmp_path / "library"
    pid = "E2"
    write_card(library, pid, title="E2", doi="", findings=["F1."])
    write_elements(library, pid, [
        {"facet": "analysis", "surface": "test", "quote": "q",
         "reading_block_id": "E2-RB-0001", "role": "used"},
    ])
    write_paper_syntheses(library, pid, [
        {"synthesis_id": "E2-SYN-0001", "synthesis_type": "method_result_link",
         "claim": "explicit link", "supporting_evidence_atom_ids": ["X"]},
    ])
    view = assemble_decomposition(library / pid)

    assert view["source"] == "elements"
    rels = view["result_relations"]
    assert len(rels) == 1
    assert rels[0]["synthesis_id"] == "E2-SYN-0001"


def test_elements_payload_key_superset_of_legacy(tmp_path: Path):
    """elements payload must expose every documented legacy key plus 'source'."""
    paper_dir = _elements_paper(tmp_path / "library")
    view = assemble_decomposition(paper_dir)
    assert _LEGACY_PAYLOAD_KEYS.issubset(view.keys())
    assert "source" in view


def test_legacy_source_when_no_elements(tmp_path: Path):
    """Legacy path: no elements.json → source=='legacy', existing atoms still work."""
    library = tmp_path / "library"
    paper_dir = _full_paper(library)
    view = assemble_decomposition(paper_dir)

    assert view["source"] == "legacy"
    # existing assertions still hold
    assert {a["evidence_atom_id"] for a in view["analyses"]} == {"S1-EVATOM-0001"}
    assert {a["evidence_atom_id"] for a in view["results"]} == {"S1-EVATOM-0002", "S1-EVATOM-0003"}


def test_elements_empty_occurrences_falls_back_to_legacy(tmp_path: Path):
    """elements.json present but occurrences empty → legacy path, source=='legacy'."""
    library = tmp_path / "library"
    pid = "E3"
    write_card(library, pid, title="E3", doi="")
    write_elements(library, pid, [])  # empty occurrences → None from helper
    write_evidence_atoms(library, pid, [
        {"evidence_atom_id": "E3-EVATOM-0001", "atom_type": "method",
         "minimal_claim": "GCMC", "quote": "q", "reading_block_id": "E3-RB-0001", "confidence": "high"},
    ])
    view = assemble_decomposition(library / pid)

    assert view["source"] == "legacy"
    assert len(view["analyses"]) == 1
    assert view["analyses"][0]["evidence_atom_id"] == "E3-EVATOM-0001"


def test_elements_all_mentioned_falls_back_to_legacy(tmp_path: Path):
    """elements.json with occurrences all role='mentioned' → projection empty → legacy path.

    Reproduces the 24-paper all-mentioned-review scenario: even though elements.json
    has entries, no 'used' occurrence maps to any analysis/result facet, so
    _elements_views returns None and assemble_decomposition uses evidence_atoms.
    """
    library = tmp_path / "library"
    pid = "E4"
    write_card(library, pid, title="Review Paper", doi="")
    write_elements(library, pid, [
        # all role='mentioned' — none are 'used', so projection produces nothing
        {"facet": "analysis", "surface": "regression", "quote": "q1",
         "reading_block_id": "E4-RB-0001", "role": "mentioned"},
        {"facet": "finding", "surface": "T rises", "quote": "q2",
         "reading_block_id": "E4-RB-0001", "role": "mentioned"},
        # material facet 'used' — not in analysis/result facets, also excluded
        {"facet": "material", "surface": "silica", "quote": "q3",
         "reading_block_id": "E4-RB-0001", "role": "used"},
    ])
    write_evidence_atoms(library, pid, [
        {"evidence_atom_id": "E4-EVATOM-0001", "atom_type": "method",
         "minimal_claim": "GCMC simulation", "quote": "We used GCMC.",
         "reading_block_id": "E4-RB-0001", "confidence": "high"},
    ])
    view = assemble_decomposition(library / pid)

    # must fall back to legacy because element projection was empty
    assert view["source"] == "legacy"
    # legacy atoms should still be present
    assert len(view["analyses"]) == 1
    assert view["analyses"][0]["evidence_atom_id"] == "E4-EVATOM-0001"


def test_characterization_and_preparation_in_analyses(tmp_path: Path):
    """Occurrences with facet 'characterization' or 'preparation' appear in analyses.

    M-3 broadening: user journey requires experimental-method detail including
    characterization (e.g. XRD) and preparation (e.g. ball-milling).
    """
    library = tmp_path / "library"
    pid = "E5"
    write_card(library, pid, title="Synthesis Study", doi="")
    write_elements(library, pid, [
        {"facet": "characterization", "surface": "XRD analysis", "quote": "XRD was used.",
         "reading_block_id": "E5-RB-0001", "role": "used"},
        {"facet": "preparation", "surface": "ball-milling", "quote": "milled for 2 h.",
         "reading_block_id": "E5-RB-0001", "role": "used"},
        # finding still goes to results
        {"facet": "finding", "surface": "Phase purity confirmed.", "quote": "pure phase.",
         "reading_block_id": "E5-RB-0001", "role": "used"},
    ])
    view = assemble_decomposition(library / pid)

    assert view["source"] == "elements"

    analysis_facets = {a["atom_type"] for a in view["analyses"]}
    assert "characterization" in analysis_facets, f"Got facets: {analysis_facets}"
    assert "preparation" in analysis_facets, f"Got facets: {analysis_facets}"

    # each atom's atom_type matches its declared facet
    xrd_atoms = [a for a in view["analyses"] if a["atom_type"] == "characterization"]
    assert xrd_atoms[0]["minimal_claim"] == "XRD analysis"

    mill_atoms = [a for a in view["analyses"] if a["atom_type"] == "preparation"]
    assert mill_atoms[0]["minimal_claim"] == "ball-milling"

    # finding still lands in results, not analyses
    result_facets = {r["atom_type"] for r in view["results"]}
    assert result_facets == {"finding"}
