from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from autoreview_app import settings as app_settings
from autoreview_app.api import _default_bootstrap_runner, create_app
from autoreview_app.config import AppConfig


def _client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(AppConfig(library_dir=tmp_path / "library")))


# ---------------------------------------------------------------- storage ----

def test_parallel_defaults_when_file_missing(tmp_path: Path):
    path = tmp_path / "app_settings.json"
    assert app_settings.get_parallel(path) == {"flash": 2500, "pro": 500}


def test_parallel_roundtrip(tmp_path: Path):
    path = tmp_path / "app_settings.json"
    stored = app_settings.set_parallel(path, flash=64, pro=8)
    assert stored == {"flash": 64, "pro": 8}
    assert app_settings.get_parallel(path) == {"flash": 64, "pro": 8}


def test_parallel_rejects_out_of_range(tmp_path: Path):
    path = tmp_path / "app_settings.json"
    with pytest.raises(ValueError):
        app_settings.set_parallel(path, flash=0, pro=8)
    with pytest.raises(ValueError):
        app_settings.set_parallel(path, flash=2501, pro=8)
    with pytest.raises(ValueError):
        app_settings.set_parallel(path, flash=64, pro=501)
    with pytest.raises(ValueError):
        app_settings.set_parallel(path, flash=True, pro=8)  # bool is not a count


def test_parallel_survives_corrupt_file(tmp_path: Path):
    path = tmp_path / "app_settings.json"
    path.write_text("{not json", encoding="utf-8")
    assert app_settings.get_parallel(path) == {"flash": 2500, "pro": 500}
    app_settings.set_parallel(path, flash=10, pro=10)  # heals the file
    assert app_settings.get_parallel(path) == {"flash": 10, "pro": 10}


def test_parallel_for_model_tiers(tmp_path: Path):
    path = tmp_path / "app_settings.json"
    app_settings.set_parallel(path, flash=128, pro=16)
    assert app_settings.parallel_for_model(path, "deepseek-v4-flash") == 128
    assert app_settings.parallel_for_model(path, "deepseek-v4-pro") == 16
    assert app_settings.parallel_for_model(path, "DeepSeek-V4-PRO") == 16
    assert app_settings.parallel_for_model(path, "") == 128  # unknown -> flash tier


# -------------------------------------------------------------------- API ----

def test_parallel_api_get_defaults_then_put(tmp_path: Path):
    client = _client(tmp_path)
    body = client.get("/settings/parallel").json()
    assert body["flash"] == 2500 and body["pro"] == 500
    assert body["limits"] == {"flash": 2500, "pro": 500}

    resp = client.put("/settings/parallel", json={"flash": 32, "pro": 4})
    assert resp.status_code == 200
    body = client.get("/settings/parallel").json()
    assert body["flash"] == 32 and body["pro"] == 4


def test_parallel_api_rejects_out_of_range(tmp_path: Path):
    client = _client(tmp_path)
    assert client.put("/settings/parallel", json={"flash": 0, "pro": 4}).status_code == 400
    assert client.put("/settings/parallel", json={"flash": 9999, "pro": 4}).status_code == 400
    assert client.put("/settings/parallel", json={"flash": 32, "pro": 999}).status_code == 400
    # nothing was stored by the rejected calls
    assert client.get("/settings/parallel").json()["flash"] == 2500


# ------------------------------------------------- bootstrap runner wiring ----

def test_bootstrap_runner_uses_configured_parallel(tmp_path: Path, monkeypatch):
    config = AppConfig(library_dir=tmp_path / "library")
    app_settings.set_parallel(config.app_settings_path, flash=77, pro=7)

    class _FakeCfg:
        model = "deepseek-v4-flash"

    class _FakeClient:
        config = _FakeCfg()

    import autoreview_app.ai.client as ai_client_mod
    import autoreview_app.elements.service as service_mod

    monkeypatch.setattr(ai_client_mod, "build_ai_client", lambda root: _FakeClient())

    captured: dict = {}

    def fake_bootstrap(cfg, client, report, parallel):
        captured["parallel"] = parallel
        return {"ok": True}

    monkeypatch.setattr(service_mod, "run_bootstrap", fake_bootstrap)

    out = _default_bootstrap_runner(config)(lambda msg: None)
    assert out == {"ok": True}
    assert captured["parallel"] == 77


def test_bootstrap_runner_pro_model_uses_pro_tier(tmp_path: Path, monkeypatch):
    config = AppConfig(library_dir=tmp_path / "library")
    app_settings.set_parallel(config.app_settings_path, flash=77, pro=7)

    class _FakeCfg:
        model = "deepseek-v4-pro"

    class _FakeClient:
        config = _FakeCfg()

    import autoreview_app.ai.client as ai_client_mod
    import autoreview_app.elements.service as service_mod

    monkeypatch.setattr(ai_client_mod, "build_ai_client", lambda root: _FakeClient())

    captured: dict = {}

    def fake_bootstrap(cfg, client, report, parallel):
        captured["parallel"] = parallel
        return {"ok": True}

    monkeypatch.setattr(service_mod, "run_bootstrap", fake_bootstrap)

    _default_bootstrap_runner(config)(lambda msg: None)
    assert captured["parallel"] == 7
