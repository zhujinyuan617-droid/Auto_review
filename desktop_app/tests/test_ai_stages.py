import json
from pathlib import Path

from _fake_ai import SequencedFakeClient
from _pdf_helpers import make_pdf

from autoreview_app.engine_bridge import build_package_from_pdf
from autoreview_app.extract.pymupdf_extractor import PyMuPDFExtractor
from autoreview_app.ai.stages import run_ai_pipeline


def _seed_package(tmp_path: Path) -> Path:
    pdf = make_pdf(tmp_path / "p.pdf", ["Intro: the problem is X.", "Methods: we did Y. Result: Z."])
    library = tmp_path / "library"
    build_package_from_pdf(
        pdf_path=pdf, library_dir=library, docling_json_dir=tmp_path / "dj",
        extractor=PyMuPDFExtractor(),
    )
    return library / "S1"


def _canned(paper_dir: Path):
    content = json.loads((paper_dir / "content_blocks.json").read_text(encoding="utf-8"))
    block_ids = [b["block_id"] for b in content["blocks"]]
    paper_id = content["paper_id"]
    sections = {
        "paper_id": paper_id,
        "sections": [{
            "section_id": f"{paper_id}-AISEC-001", "order": 1, "title": "Body",
            "section_kind": "introduction", "page_start": 1, "page_end": 2,
            "block_ids": block_ids, "notes": "",
        }],
        "warnings": [],
    }
    reading = {
        "paper_id": paper_id,
        "reading_blocks": [{
            "section_id": f"{paper_id}-AISEC-001", "reading_type": "paragraph",
            "source_block_ids": block_ids, "join_reason": "same paragraph", "confidence": 0.9,
        }],
        "warnings": [],
    }
    card = {
        "paper": {"title": "A Study of Z", "doi": "", "year": "2020", "journal": "", "paper_type": "article"},
        "classification": {"research_objects": ["X"], "methods": ["Y"], "domain_tags": ["z"], "gas_systems": [], "scale": []},
        "summary": {"objective": "Investigate X.", "main_findings": ["Z happens."], "methods_systems": "Y"},
        "ai_warnings": [],
    }
    return [sections, reading, card]


def test_run_ai_pipeline_produces_card(tmp_path: Path):
    paper_dir = _seed_package(tmp_path)
    client = SequencedFakeClient(_canned(paper_dir))

    run_ai_pipeline(paper_dir, client)

    assert client.call_count == 3  # sections, reading, card
    assert (paper_dir / "ai_sections.json").exists()
    assert (paper_dir / "reading_blocks.json").exists()

    card = json.loads((paper_dir / "literature_card.json").read_text(encoding="utf-8"))
    assert card["schema_version"] == "0.2.0"
    assert card["paper"]["title"] == "A Study of Z"
    assert card["summary"]["main_findings"] == ["Z happens."]
