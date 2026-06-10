from pathlib import Path

from fastapi.testclient import TestClient

from _library_fixtures import write_card, write_elements, write_reading_blocks

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(library: Path):
    return TestClient(create_app(AppConfig(library_dir=library)))


def test_decomposition_endpoint(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="Methane Study", doi="10.1/a")
    write_reading_blocks(library, "S1", [
        {"reading_block_id": "S1-RB-0001", "section_kind": "abstract", "text": "We study methane."},
    ])

    resp = _client(library).get("/papers/S1/decomposition")
    assert resp.status_code == 200
    body = resp.json()
    assert body["paper_id"] == "S1"
    assert body["card"]["title"] == "Methane Study"
    assert body["abstract_blocks"][0]["text"] == "We study methane."


def test_decomposition_unknown_paper_404(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="X")
    assert _client(library).get("/papers/missing/decomposition").status_code == 404


def test_decomposition_endpoint_exposes_source_field(tmp_path: Path):
    """API route must include 'source' in the response body (legacy or elements)."""
    library = tmp_path / "library"
    write_card(library, "S2", title="Source Test", doi="")
    resp = _client(library).get("/papers/S2/decomposition")
    assert resp.status_code == 200
    assert "source" in resp.json()


def test_decomposition_endpoint_elements_source(tmp_path: Path):
    """When elements.json present, API route returns source=='elements'."""
    library = tmp_path / "library"
    write_card(library, "S3", title="Elements Test", doi="",
               findings=["A finding."])
    write_elements(library, "S3", [
        {"facet": "analysis", "surface": "DFT",
         "quote": "DFT was used.", "reading_block_id": "S3-RB-0001", "role": "used"},
    ])
    resp = _client(library).get("/papers/S3/decomposition")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "elements"
    assert len(body["analyses"]) == 1
    assert body["analyses"][0]["minimal_claim"] == "DFT"


# ---------------------------------------------------------------------------
# Wave-3 ③:PDF 投递 / 原文段锚点数据面 / condition 上屏
# ---------------------------------------------------------------------------


def test_paper_pdf_served_inline_and_404(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="PDF Test")
    (library / "S1" / "source.pdf").write_bytes(b"%PDF-1.4 fake body")
    client = _client(library)
    resp = client.get("/papers/S1/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    write_card(library, "S2", title="No PDF")
    assert client.get("/papers/S2/pdf").status_code == 404
    assert client.get("/papers/../escape/pdf").status_code == 404


def test_paper_block_context(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="Block Test")
    write_reading_blocks(library, "S1", [
        {"reading_block_id": "S1-RB-0001", "section_kind": "abstract",
         "section_title": "Abstract", "text": "First.", "page_start": 1},
        {"reading_block_id": "S1-RB-0002", "section_kind": "introduction",
         "section_title": "Introduction", "text": "Second.", "page_start": 1},
        {"reading_block_id": "S1-RB-0003", "section_kind": "introduction",
         "section_title": "Introduction", "text": "Third.", "page_start": 2},
    ])
    client = _client(library)
    body = client.get("/papers/S1/blocks/S1-RB-0002").json()
    assert body["block"]["text"] == "Second."
    assert body["block"]["section_title"] == "Introduction"
    assert body["prev"]["reading_block_id"] == "S1-RB-0001"
    assert body["next"]["text"] == "Third."
    first = client.get("/papers/S1/blocks/S1-RB-0001").json()
    assert first["prev"] is None
    assert client.get("/papers/S1/blocks/S1-RB-9999").status_code == 404


def test_decomposition_conditions_on_screen(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S4", title="Cond Test")
    write_elements(library, "S4", [
        {"facet": "analysis", "surface": "GCMC",
         "quote": "GCMC was used.", "reading_block_id": "S4-RB-0001", "role": "used"},
        {"facet": "condition", "surface": "temperature",
         "quote": "at 300 K and 10 MPa", "reading_block_id": "S4-RB-0002", "role": "used",
         "values": [{"raw": "300 K"}, {"raw": "10 MPa"}]},
        {"facet": "condition", "surface": "pressure", "quote": "mentioned only",
         "reading_block_id": "S4-RB-0003", "role": "mentioned"},
    ])
    body = _client(library).get("/papers/S4/decomposition").json()
    assert body["source"] == "elements"
    conds = body["conditions"]
    assert len(conds) == 1  # mentioned 不上屏
    assert conds[0]["minimal_claim"] == "temperature"
    assert conds[0]["values"] == ["300 K", "10 MPa"]
    # condition 不再混进 analyses
    assert all(a["atom_type"] != "condition" for a in body["analyses"])
