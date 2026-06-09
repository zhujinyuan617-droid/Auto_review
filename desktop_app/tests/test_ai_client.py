from pathlib import Path

from autoreview_app.ai.client import build_ai_client


def test_build_ai_client_from_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("DOCDECOMP_AI_BASE_URL", "http://fake.local")
    monkeypatch.setenv("DOCDECOMP_AI_API_KEY", "fake-key")
    monkeypatch.setenv("DOCDECOMP_AI_MODEL", "fake-model")

    client = build_ai_client(config_root=tmp_path)

    assert client.config.base_url == "http://fake.local"
    assert client.config.api_key == "fake-key"
    assert client.config.model == "fake-model"
    assert hasattr(client, "chat_json")


def test_build_ai_client_prefers_keyring(tmp_path, monkeypatch):
    import autoreview_app.ai.client as client_mod
    monkeypatch.setattr(client_mod.app_settings, "get_api_key", lambda: "sk-keyring-xyz")
    monkeypatch.delenv("DOCDECOMP_AI_API_KEY", raising=False)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "ai.local.json").write_text(
        '{"base_url":"https://api.deepseek.com","api_key":"sk-file-old","model":"deepseek-v4-flash"}',
        encoding="utf-8",
    )
    c = client_mod.build_ai_client(tmp_path)
    assert c.config.api_key == "sk-keyring-xyz"


def test_build_ai_client_env_beats_keyring(tmp_path, monkeypatch):
    import autoreview_app.ai.client as client_mod
    monkeypatch.setattr(client_mod.app_settings, "get_api_key", lambda: "sk-keyring-xyz")
    monkeypatch.setenv("DOCDECOMP_AI_API_KEY", "sk-env-wins")
    cfg_dir = tmp_path / "config"; cfg_dir.mkdir()
    (cfg_dir / "ai.local.json").write_text(
        '{"base_url":"https://api.deepseek.com","api_key":"sk-file","model":"m"}', encoding="utf-8")
    c = client_mod.build_ai_client(tmp_path)
    assert c.config.api_key == "sk-env-wins"
