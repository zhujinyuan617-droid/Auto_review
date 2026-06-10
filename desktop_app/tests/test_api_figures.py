import json
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig

# 1x1 PNG
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8cfc000000301010018dd8db00000000049454e44ae426082")


def _setup(tmp_path: Path) -> tuple[TestClient, AppConfig]:
    cfg = AppConfig(library_dir=tmp_path / "library")
    d = cfg.library_dir / "S01" / "figures"
    d.mkdir(parents=True)
    (d / "fig1.png").write_bytes(_PNG)
    (d / "fig2.jpg").write_bytes(_PNG)
    (d / "notes.txt").write_text("not an image", encoding="utf-8")
    (cfg.library_dir / "S01" / "literature_card.json").write_text(
        json.dumps({"paper_id": "S01", "paper": {}, "classification": {}}), encoding="utf-8")
    return TestClient(create_app(cfg)), cfg


def test_figures_list_images_only(tmp_path: Path):
    client, _ = _setup(tmp_path)
    body = client.get("/papers/S01/figures").json()
    assert body["figures"] == ["fig1.png", "fig2.jpg"]  # txt 不入列


def test_figures_empty_when_no_dir(tmp_path: Path):
    client, cfg = _setup(tmp_path)
    (cfg.library_dir / "S02").mkdir()
    (cfg.library_dir / "S02" / "literature_card.json").write_text("{}", encoding="utf-8")
    assert client.get("/papers/S02/figures").json()["figures"] == []


def test_figure_file_served(tmp_path: Path):
    client, _ = _setup(tmp_path)
    resp = client.get("/papers/S01/figures/fig1.png")
    assert resp.status_code == 200
    assert resp.content == _PNG


def test_figure_traversal_and_nonimage_blocked(tmp_path: Path):
    client, _ = _setup(tmp_path)
    assert client.get("/papers/S01/figures/notes.txt").status_code == 404
    assert client.get("/papers/S01/figures/..%2Fliterature_card.json").status_code == 404
    assert client.get("/papers/..%2FS01/figures").status_code == 404
    assert client.get("/papers/S01/figures/missing.png").status_code == 404
