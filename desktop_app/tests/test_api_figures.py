import json
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig

# 1x1 PNG(尺寸过滤口径下 = 垃圾图;真图用 _png_header 伪造大尺寸头)
_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de"
    "0000000c4944415408d763f8cfc000000301010018dd8db00000000049454e44ae426082")


def _png_header(w: int, h: int) -> bytes:
    """只伪造签名+IHDR 宽高(接口只读头,不解码全图)。"""
    return (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR"
            + w.to_bytes(4, "big") + h.to_bytes(4, "big") + b"\x08\x02\x00\x00\x00")


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


def test_figures_tiny_junk_hidden_txt_excluded(tmp_path: Path):
    # 用户拍板:出版社杂项(无图注小图)彻底不显示;1x1 PNG 即垃圾画像
    client, _ = _setup(tmp_path)
    body = client.get("/papers/S01/figures").json()
    assert body["figures"] == []
    assert body["hidden"] == 2  # fig1.png + fig2.jpg(同为 PNG 字节);txt 根本不算图


def test_figures_captions_and_junk_rules(tmp_path: Path):
    client, cfg = _setup(tmp_path)
    d = cfg.library_dir / "S01" / "figures"
    (d / "real.png").write_bytes(_png_header(800, 600))       # 大图,带图注
    (d / "abstract.png").write_bytes(_png_header(1000, 400))  # 首页大图(graphical abstract)无注:保留
    (d / "badge.png").write_bytes(_png_header(200, 200))      # 首页中图无注:出版社徽章,过滤
    (cfg.library_dir / "S01" / "content_blocks.json").write_text(json.dumps({
        "blocks": [
            {"type": "figure", "page_no": "3", "caption": "Fig. 1. FTIR spectra.",
             "image_path": "figures/real.png"},
            {"type": "figure", "page_no": "1", "caption": "", "image_path": "figures/abstract.png"},
            {"type": "figure", "page_no": "1", "caption": "", "image_path": "figures/badge.png"},
        ]}), encoding="utf-8")
    body = client.get("/papers/S01/figures").json()
    by_name = {f["name"]: f for f in body["figures"]}
    assert "real.png" in by_name and by_name["real.png"]["caption"] == "Fig. 1. FTIR spectra."
    assert by_name["real.png"]["page"] == 3
    assert "abstract.png" in by_name  # 首页大图不杀
    assert "badge.png" not in by_name  # 首页无注中图 = 杂项
    assert body["hidden"] == 3  # badge + 两张 1x1


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
