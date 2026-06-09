from pathlib import Path

import keyring
import pytest
from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


@pytest.fixture(autouse=True)
def memory_keyring(monkeypatch):
    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(keyring, "set_password", lambda s, u, p: store.__setitem__((s, u), p))
    monkeypatch.setattr(keyring, "get_password", lambda s, u: store.get((s, u)))
    monkeypatch.setattr(keyring, "delete_password", lambda s, u: store.pop((s, u), None))
    return store


def _client(tmp_path: Path):
    return TestClient(create_app(AppConfig(library_dir=tmp_path / "library")))


def test_apikey_lifecycle_never_leaks_key(tmp_path: Path):
    client = _client(tmp_path)
    assert client.get("/settings/apikey").json() == {"configured": False}

    resp = client.post("/settings/apikey", json={"api_key": "sk-secret-xyz"})
    assert resp.status_code == 200
    assert "sk-secret-xyz" not in resp.text
    assert client.get("/settings/apikey").json() == {"configured": True}

    client.delete("/settings/apikey")
    assert client.get("/settings/apikey").json() == {"configured": False}


def test_blank_apikey_returns_400(tmp_path: Path):
    resp = _client(tmp_path).post("/settings/apikey", json={"api_key": "   "})
    assert resp.status_code == 400
    assert _client(tmp_path).get("/settings/apikey").json() == {"configured": False}


def test_setup_manifest_endpoint(tmp_path: Path):
    body = _client(tmp_path).get("/settings/setup-manifest").json()
    assert body["consent_required"] is True
    assert body["will_install"]
