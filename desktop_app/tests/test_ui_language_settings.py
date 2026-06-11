# desktop_app/tests/test_ui_language_settings.py
import json
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig
from autoreview_app import settings as app_settings


def test_get_set_ui_language_unit(tmp_path: Path):
    p = tmp_path / "app_settings.json"
    assert app_settings.get_ui_language(p) == "zh"          # 默认中文
    assert app_settings.set_ui_language(p, "en") == "en"
    assert app_settings.get_ui_language(p) == "en"
    try:
        app_settings.set_ui_language(p, "fr")
        raise AssertionError("should raise ValueError")
    except ValueError:
        pass
    # 与同文件其他键共存,互不覆盖
    data = json.loads(p.read_text(encoding="utf-8"))
    data["parallel"] = {"flash": 9, "pro": 9}
    p.write_text(json.dumps(data), encoding="utf-8")
    app_settings.set_ui_language(p, "zh")
    assert json.loads(p.read_text(encoding="utf-8"))["parallel"] == {"flash": 9, "pro": 9}


def test_language_api_roundtrip(tmp_path: Path):
    client = TestClient(create_app(AppConfig(library_dir=tmp_path / "library")))
    assert client.get("/settings/language").json() == {"ui_language": "zh"}
    assert client.put("/settings/language", json={"ui_language": "en"}).status_code == 200
    assert client.get("/settings/language").json() == {"ui_language": "en"}
    assert client.put("/settings/language", json={"ui_language": "xx"}).status_code == 400
