"""导入链作者机构兜底:card.authors_raw -> authorship.json + 注册表追加。"""
import json
from pathlib import Path

from autoreview_app.authorship_fallback import authorship_from_card


def _card(d: Path, authors_raw):
    d.mkdir(parents=True, exist_ok=True)
    (d / "literature_card.json").write_text(json.dumps({
        "paper_id": d.name, "paper": {}, "classification": {},
        "authors_raw": authors_raw}), encoding="utf-8")


def test_fallback_writes_authorship_and_registers_institutions(tmp_path: Path):
    lib = tmp_path / "library"
    reg = tmp_path / "data" / "institutions" / "registry.json"
    _card(lib / "S01", [
        {"name": "Alice Li", "is_senior": False, "affiliations": ["Alpha University"]},
        {"name": "Bob Wang", "is_senior": True,
         "affiliations": ["Alpha University", "Beta Institute"]},
    ])
    assert authorship_from_card(lib / "S01", reg) is True
    doc = json.loads((lib / "S01" / "authorship.json").read_text(encoding="utf-8"))
    assert doc["source"] == "card-ai"
    assert doc["authors"][1]["is_senior"] is True
    assert doc["authors"][0]["institution_ids"] == ["elem:institution/alpha-university"]
    entries = json.loads(reg.read_text(encoding="utf-8"))["entries"]
    assert entries["elem:institution/beta-institute"]["origin"] == "card-ai"
    assert len(entries) == 2
    # 同名机构复用条目,不重复注册
    _card(lib / "S02", [{"name": "C", "is_senior": True, "affiliations": ["alpha university"]}])
    assert authorship_from_card(lib / "S02", reg) is True
    assert len(json.loads(reg.read_text(encoding="utf-8"))["entries"]) == 2


def test_fallback_skips_when_authorship_exists_or_no_authors(tmp_path: Path):
    lib = tmp_path / "library"
    reg = tmp_path / "reg.json"
    _card(lib / "S03", [])
    assert authorship_from_card(lib / "S03", reg) is False  # 无 authors_raw
    _card(lib / "S04", [{"name": "D", "affiliations": []}])
    (lib / "S04" / "authorship.json").write_text("{}", encoding="utf-8")
    assert authorship_from_card(lib / "S04", reg) is False  # OpenAlex 已有,不覆盖
