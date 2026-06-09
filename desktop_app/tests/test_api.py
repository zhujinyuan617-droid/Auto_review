from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(library_dir: Path) -> TestClient:
    return TestClient(create_app(AppConfig(library_dir=library_dir)))


def test_health_ok(tmp_path: Path):
    response = _client(tmp_path).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_library_empty(tmp_path: Path):
    response = _client(tmp_path).get("/library")
    assert response.status_code == 200
    assert response.json() == {"papers": []}


def test_library_lists_papers(tmp_path: Path):
    (tmp_path / "S01").mkdir()
    response = _client(tmp_path).get("/library")
    assert response.json() == {"papers": ["S01"]}
