from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(tmp_path: Path):
    return TestClient(create_app(AppConfig(library_dir=tmp_path / "library")))


def test_check_clean_draft(tmp_path: Path):
    resp = _client(tmp_path).post("/writing/check", json={"draft": "Adsorption rises [S09]."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["citation"]["passed"] is True
    assert body["style"]["warnings"] == []


def test_check_flags_bare_citation(tmp_path: Path):
    resp = _client(tmp_path).post("/writing/check", json={"draft": "Adsorption rises S09."})
    assert resp.status_code == 200
    assert resp.json()["citation"]["passed"] is False
