from pathlib import Path

from _library_fixtures import (
    write_card,
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
