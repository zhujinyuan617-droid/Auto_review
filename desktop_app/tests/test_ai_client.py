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
