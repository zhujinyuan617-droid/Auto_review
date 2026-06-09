from pathlib import Path

from fastapi.testclient import TestClient

from _library_fixtures import write_card, write_reading_blocks

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
