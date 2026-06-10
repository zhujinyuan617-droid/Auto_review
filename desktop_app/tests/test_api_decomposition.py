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
