from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig

SAMPLE_RIS = "TY  - JOUR\nTI  - Hello Paper\nDO  - 10.1/x\nER  -\n"


def _client(tmp_path: Path, search_runner=None):
    app = create_app(AppConfig(library_dir=tmp_path / "library"), search_runner=search_runner)
    return TestClient(app)


def test_import_ris_returns_records(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.post("/discovery/import-ris", json={"text": SAMPLE_RIS})
    assert resp.status_code == 200
    records = resp.json()["records"]
    assert records[0]["title"] == "Hello Paper"
    assert records[0]["doi"] == "10.1/x"


def test_search_uses_injected_runner(tmp_path: Path):
    def fake_search(query: str):
        return [{"title": f"result for {query}", "doi": "10.1/q", "year": "", "journal": "", "authors": [], "pdf_url": ""}]

    client = _client(tmp_path, search_runner=fake_search)
    resp = client.post("/discovery/search", json={"query": "methane"})
    assert resp.status_code == 200
    assert resp.json()["records"][0]["title"] == "result for methane"
