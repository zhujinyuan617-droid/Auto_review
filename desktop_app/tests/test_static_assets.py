from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(library_dir: Path) -> TestClient:
    return TestClient(create_app(AppConfig(library_dir=library_dir)))


def test_app_js_served(tmp_path: Path):
    # app.js lives in the real repo frontend dir, independent of library_dir.
    response = _client(tmp_path).get("/assets/app.js")
    assert response.status_code == 200
    assert "render" in response.text  # the router calls each view's render()


def test_styles_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/styles.css")
    assert response.status_code == 200


def test_helper_modules_served(tmp_path: Path):
    client = _client(tmp_path)
    assert client.get("/assets/api.js").status_code == 200
    assert client.get("/assets/ui.js").status_code == 200


def test_papers_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/papers.js")
    assert response.status_code == 200
    assert "renderList" in response.text


def test_settings_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/settings.js")
    assert response.status_code == 200
    assert "apiKeySection" in response.text


def test_network_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/network.js")
    assert response.status_code == 200
    assert "network.title" in response.text


def test_writing_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/writing.js")
    assert response.status_code == 200
    assert "checkSection" in response.text


def test_import_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/import.js")
    assert response.status_code == 200
    assert "pollJob" in response.text


def test_groups_view_served(tmp_path: Path):
    response = _client(tmp_path).get("/assets/views/groups.js")
    assert response.status_code == 200
    assert "groups.title" in response.text
