import json
from pathlib import Path

from autoreview_app.language_gate import check_package_language, cjk_ratio


def _package(tmp_path: Path, paper_id: str, texts: list[str]) -> Path:
    paper_dir = tmp_path / paper_id
    paper_dir.mkdir(parents=True)
    blocks = [{"block_id": f"{paper_id}-BLK-{i:04d}", "text": t} for i, t in enumerate(texts)]
    (paper_dir / "content_blocks.json").write_text(
        json.dumps({"paper_id": paper_id, "blocks": blocks}, ensure_ascii=False), encoding="utf-8")
    return paper_dir


def test_cjk_ratio():
    assert cjk_ratio("pure english text") == 0.0
    assert cjk_ratio("纯中文文本") == 1.0
    assert 0.4 < cjk_ratio("ab中文cd文本测试ef") < 0.6  # 6 CJK / 14 CJK+ASCII ≈ 0.43


def test_english_package_passes(tmp_path: Path):
    paper_dir = _package(tmp_path, "S90", ["Methane adsorption on clay.", "XRD was used."])
    gate = check_package_language(paper_dir)
    assert gate["deferred"] is False


def test_chinese_package_deferred(tmp_path: Path):
    paper_dir = _package(tmp_path, "S91", ["页岩气吸附机理研究", "蒙脱石的甲烷吸附等温线测定", "Abstract"])
    gate = check_package_language(paper_dir)
    assert gate["deferred"] is True
    assert gate["cjk_ratio"] > 0.15


def test_import_pdf_stops_before_ai_on_cjk(tmp_path: Path, monkeypatch):
    """import_pdf must write language_gate.json and skip AI stages for CJK papers."""
    from autoreview_app import importer

    def fake_build(pdf_path, library_dir, docling_json_dir, extractor):
        _package(library_dir, "S91", ["页岩气吸附机理研究综述,中文正文内容很长。" * 20])
        return "S91"

    monkeypatch.setattr(importer, "build_package_from_pdf", fake_build)

    def explode(*a, **k):
        raise AssertionError("AI pipeline must not run for deferred CJK paper")

    monkeypatch.setattr(importer, "run_ai_pipeline", explode)
    progress: list[str] = []
    paper_id = importer.import_pdf(Path("fake.pdf"), tmp_path, tmp_path / "docling",
                                   extractor=None, client_factory=lambda d: None,
                                   progress=progress.append)
    assert paper_id == "S91"
    assert (tmp_path / "S91" / "language_gate.json").exists()
    assert any("deferred" in m for m in progress)
