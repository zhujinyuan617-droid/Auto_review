from pathlib import Path

from autoreview_app.config import AppConfig


def test_from_env_uses_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("AUTOREVIEW_LIBRARY_DIR", str(tmp_path / "mylib"))
    config = AppConfig.from_env()
    assert config.library_dir == tmp_path / "mylib"


def test_from_env_default_is_cwd_library(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("AUTOREVIEW_LIBRARY_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    config = AppConfig.from_env()
    assert config.library_dir == tmp_path / "library"
