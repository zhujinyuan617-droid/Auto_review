import json
from pathlib import Path

from _pdf_helpers import make_pdf

from autoreview_app.engine_bridge import build_package_from_pdf
from autoreview_app.extract.pymupdf_extractor import PyMuPDFExtractor
from autoreview_app.library_index import list_papers


def test_pdf_becomes_a_valid_clean_package(tmp_path: Path):
    pdf = make_pdf(tmp_path / "mypaper.pdf", ["Hello abstract world.", "Methods section here."])
    library = tmp_path / "library"
    docling_dir = tmp_path / "docling_json"

    paper_id = build_package_from_pdf(
        pdf_path=pdf,
        library_dir=library,
        docling_json_dir=docling_dir,
        extractor=PyMuPDFExtractor(),
    )

    assert paper_id == "S1"
    paper_dir = library / paper_id

    content = json.loads((paper_dir / "content_blocks.json").read_text(encoding="utf-8"))
    assert content["paper_id"] == "S1"
    blocks_text = " ".join(b.get("text", "") for b in content["blocks"])
    assert "Hello abstract world." in blocks_text

    assert (paper_dir / "evidence.json").exists()
    assert (paper_dir / "metadata_candidates.json").exists()
    assert (paper_dir / "content.md").read_text(encoding="utf-8").strip()

    assert list_papers(library) == ["S1"]


def test_second_import_gets_next_id(tmp_path: Path):
    library = tmp_path / "library"
    docling_dir = tmp_path / "docling_json"
    first = make_pdf(tmp_path / "a.pdf", ["First paper text."])
    second = make_pdf(tmp_path / "b.pdf", ["Second paper text."])

    id1 = build_package_from_pdf(
        pdf_path=first, library_dir=library, docling_json_dir=docling_dir, extractor=PyMuPDFExtractor()
    )
    id2 = build_package_from_pdf(
        pdf_path=second, library_dir=library, docling_json_dir=docling_dir, extractor=PyMuPDFExtractor()
    )

    assert id1 == "S1"
    assert id2 == "S2"

    s2 = json.loads((library / "S2" / "content_blocks.json").read_text(encoding="utf-8"))
    assert "Second paper text." in " ".join(b.get("text", "") for b in s2["blocks"])
