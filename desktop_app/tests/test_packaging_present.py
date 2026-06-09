from pathlib import Path

PKG = Path(__file__).resolve().parents[1] / "packaging"
ROOT = Path(__file__).resolve().parents[1]


def test_build_scaffolding_present():
    spec = PKG / "autoreview.spec"
    build = PKG / "build.ps1"
    doc = ROOT / "PACKAGING.md"
    for path in (spec, build, doc):
        assert path.is_file(), path
        assert path.read_text(encoding="utf-8").strip(), f"{path} is empty"
    text = doc.read_text(encoding="utf-8").lower()
    assert "not verified" in text or "on your machine" in text
