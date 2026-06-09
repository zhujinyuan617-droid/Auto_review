from pathlib import Path

from _pdf_helpers import make_pdf

from autoreview_app.extract.pymupdf_extractor import PyMuPDFExtractor


def test_extracts_text_with_page_numbers(tmp_path: Path):
    pdf = make_pdf(tmp_path / "paper.pdf", ["Hello abstract world.", "Methods section here."])
    doc = PyMuPDFExtractor().extract(pdf)

    assert doc["name"] == "paper"
    assert doc["origin"]["filename"] == "paper.pdf"

    all_text = " ".join(t["text"] for t in doc["texts"])
    assert "Hello abstract world." in all_text
    assert "Methods section here." in all_text

    pages = {t["prov"][0]["page_no"] for t in doc["texts"]}
    assert pages == {1, 2}


def test_body_children_match_texts_count(tmp_path: Path):
    pdf = make_pdf(tmp_path / "p.pdf", ["One.", "Two."])
    doc = PyMuPDFExtractor().extract(pdf)
    assert len(doc["body"]["children"]) == len(doc["texts"])


def test_extractor_declares_name():
    assert PyMuPDFExtractor().name == "pymupdf"
