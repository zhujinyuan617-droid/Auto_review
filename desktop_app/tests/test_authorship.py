"""Tests for groups/authorship.py — populate_authorship + institution registry."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _library_fixtures

from _library_fixtures import write_card

from autoreview_app.groups.authorship import populate_authorship


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_content_blocks(paper_dir: Path, lines: list[str]) -> None:
    """Write content_blocks.json in the REAL production shape.

    生产格式是 dict 容器({schema_version, paper_id, source, blocks});
    早期夹具误写成裸 list,导致 dict 切片崩溃(KeyError: slice)在测试里隐身。
    """
    doc = {
        "schema_version": "0.1.0",
        "paper_id": paper_dir.name,
        "source": "test",
        "blocks": [{"text": line} for line in lines],
    }
    (paper_dir / "content_blocks.json").write_text(
        json.dumps(doc, ensure_ascii=False), encoding="utf-8"
    )


def _read_authorship(paper_dir: Path) -> dict:
    return json.loads((paper_dir / "authorship.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Test: happy path via fetch
# ---------------------------------------------------------------------------

CANNED_REC_P1 = {
    "authors": [
        {"name": "Alice Wang", "position": 1, "is_senior": False,
         "raw_affiliations": ["School of Petroleum Engineering, China University"]},
        {"name": "Bob Smith", "position": 2, "is_senior": True,
         "raw_affiliations": ["MIT Energy Lab"]},
    ],
    "source": "openalex",
}


def test_populate_authorship_writes_authorship_json(tmp_path: Path):
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")

    def fake_fetch(doi):
        if doi == "10.1/aaa":
            return CANNED_REC_P1
        return None

    result = populate_authorship(lib, inst_dir, fake_fetch)
    assert result["populated"] == 1
    assert result["failed"] == 0
    assert result["skipped_no_doi"] == 0
    assert result["pdf_fallback"] == 0

    doc = _read_authorship(lib / "S01")
    assert doc["paper_id"] == "S01"
    assert doc["source"] == "openalex"
    assert len(doc["authors"]) == 2
    assert "fetched_at" in doc


def test_populate_authorship_resolves_institution_ids(tmp_path: Path):
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")

    def fake_fetch(doi):
        return CANNED_REC_P1

    populate_authorship(lib, inst_dir, fake_fetch)
    doc = _read_authorship(lib / "S01")
    # Each author's institution_ids must be non-empty lists of strings
    assert isinstance(doc["authors"][0]["institution_ids"], list)
    assert len(doc["authors"][0]["institution_ids"]) == 1
    assert isinstance(doc["authors"][0]["institution_ids"][0], str)


def test_populate_authorship_same_institution_name_single_entry(tmp_path: Path):
    """Two papers referencing same institution name -> single registry entry."""
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")
    write_card(lib, "S02", title="B", doi="10.1/bbb")

    shared_inst = "School of Petroleum Engineering, China University"

    def fake_fetch(doi):
        return {
            "authors": [
                {"name": "Author X", "position": 1, "is_senior": True,
                 "raw_affiliations": [shared_inst]},
            ],
            "source": "openalex",
        }

    populate_authorship(lib, inst_dir, fake_fetch)

    reg = json.loads((inst_dir / "registry.json").read_text(encoding="utf-8"))
    institution_ids = [
        eid for eid, entry in reg["entries"].items()
        if entry["facet"] == "institution"
    ]
    assert len(institution_ids) == 1, "Same institution name should produce one entry"


def test_populate_authorship_skips_no_doi(tmp_path: Path):
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="")

    result = populate_authorship(lib, inst_dir, lambda doi: None)
    assert result["skipped_no_doi"] == 1
    assert result["populated"] == 0
    assert not (lib / "S01" / "authorship.json").exists()


def test_populate_authorship_fetch_exception_triggers_pdf_fallback(tmp_path: Path):
    """If fetch raises, try PDF fallback; if content_blocks has affiliation lines, write authorship."""
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")
    _make_content_blocks(
        lib / "S01",
        [
            "Title: Advanced Petroleum Research",
            "School of Petroleum Engineering, China University",
            "Some random line",
            "Another line",
        ],
    )

    def bad_fetch(doi):
        raise ConnectionError("network down")

    result = populate_authorship(lib, inst_dir, bad_fetch)
    assert result["pdf_fallback"] == 1
    assert result["populated"] == 0  # pdf fallback papers counted separately
    doc = _read_authorship(lib / "S01")
    assert doc["source"] == "pdf_front_page"
    assert isinstance(doc["raw_affiliations"], list)
    assert len(doc["raw_affiliations"]) > 0
    assert isinstance(doc["institution_ids"], list)
    assert len(doc["institution_ids"]) > 0


def test_populate_authorship_no_pdf_fallback_data_fails(tmp_path: Path):
    """If fetch raises and content_blocks has no affiliation lines, count as failed."""
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")
    _make_content_blocks(lib / "S01", ["Title only", "No affiliation here"])

    def bad_fetch(doi):
        raise ConnectionError("network down")

    result = populate_authorship(lib, inst_dir, bad_fetch)
    assert result["failed"] == 1
    assert not (lib / "S01" / "authorship.json").exists()


def test_populate_authorship_returns_none_from_fetch_with_no_content_blocks(tmp_path: Path):
    """If fetch returns None and no content_blocks.json, count as failed."""
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")

    result = populate_authorship(lib, inst_dir, lambda doi: None)
    assert result["failed"] == 1
    assert not (lib / "S01" / "authorship.json").exists()


def test_populate_authorship_registry_file_written(tmp_path: Path):
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")

    populate_authorship(lib, inst_dir, lambda doi: CANNED_REC_P1)

    reg_path = inst_dir / "registry.json"
    assert reg_path.exists()
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    assert reg["schema_version"] == "0.1.0"
    assert "entries" in reg


def test_populate_authorship_schema_keys_present(tmp_path: Path):
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")

    populate_authorship(lib, inst_dir, lambda doi: CANNED_REC_P1)
    doc = _read_authorship(lib / "S01")

    # Required top-level keys
    for key in ("paper_id", "authors", "source", "fetched_at"):
        assert key in doc, f"missing key: {key}"

    # Required per-author keys
    author = doc["authors"][0]
    for key in ("name", "position", "is_senior", "raw_affiliations", "institution_ids"):
        assert key in author, f"missing author key: {key}"


def test_populate_authorship_progress_called(tmp_path: Path):
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    for i in range(1, 12):  # 11 papers so progress fires mid-run
        write_card(lib, f"S{i:02d}", title=f"P{i}", doi=f"10.1/{i:03d}")

    messages = []
    populate_authorship(lib, inst_dir, lambda doi: CANNED_REC_P1,
                        progress=messages.append)
    assert len(messages) >= 1  # at least one progress call (at 10 + at end)


def test_populate_one_bad_paper_does_not_kill_batch(tmp_path: Path):
    """坏数据单篇隔离:S01 的 fetch 返回畸形记录(authors 含 None),
    旧实现会 AttributeError 杀全批;现在 S01 记 failed,S02 照常入库。"""
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")
    write_card(lib, "S02", title="B", doi="10.1/bbb")

    def fetch(doi):
        if doi == "10.1/aaa":
            return {"authors": [None], "source": "openalex"}  # 畸形:author 不是 dict
        return CANNED_REC_P1

    messages: list[str] = []
    result = populate_authorship(lib, inst_dir, fetch, progress=messages.append)
    assert result["failed"] == 1
    assert result["populated"] == 1
    assert not (lib / "S01" / "authorship.json").exists()
    assert (lib / "S02" / "authorship.json").exists()
    assert any("S01 failed" in m for m in messages)


def test_pdf_fallback_handles_dict_container_without_blocks(tmp_path: Path):
    """content_blocks.json 是 dict 但没有 blocks 键 → 视为不可用,计 failed 不崩。"""
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")
    (lib / "S01" / "content_blocks.json").write_text(
        json.dumps({"schema_version": "0.1.0", "paper_id": "S01"}), encoding="utf-8"
    )
    result = populate_authorship(lib, inst_dir, lambda doi: None)
    assert result["failed"] == 1
    assert not (lib / "S01" / "authorship.json").exists()


def test_populate_skips_existing_unless_force(tmp_path: Path):
    """Second run without force skips existing authorship.json; force=True re-fetches."""
    lib = tmp_path / "library"
    inst_dir = tmp_path / "data" / "institutions"
    write_card(lib, "S01", title="A", doi="10.1/aaa")
    write_card(lib, "S02", title="B", doi="10.1/bbb")

    fetch_calls: list[str] = []

    def counting_fetch(doi: str) -> dict:
        fetch_calls.append(doi)
        return CANNED_REC_P1

    # --- First run: both papers populated from scratch ---
    result1 = populate_authorship(lib, inst_dir, counting_fetch)
    assert result1["populated"] == 2
    assert result1["skipped_existing"] == 0
    assert len(fetch_calls) == 2
    fetched_at_s01_first = _read_authorship(lib / "S01")["fetched_at"]

    # --- Second run (no force): fetch must NOT be called; skipped_existing == 2 ---
    fetch_calls.clear()
    result2 = populate_authorship(lib, inst_dir, counting_fetch)
    assert len(fetch_calls) == 0, "fetch should not be called when authorship.json already exists"
    assert result2["skipped_existing"] == 2
    assert result2["populated"] == 0
    # Files must be unchanged
    assert _read_authorship(lib / "S01")["fetched_at"] == fetched_at_s01_first

    # --- Third run (force=True): fetch called again; files updated ---
    fetch_calls.clear()
    result3 = populate_authorship(lib, inst_dir, counting_fetch, force=True)
    assert len(fetch_calls) == 2, "fetch should be called for all papers when force=True"
    assert result3["populated"] == 2
    assert result3["skipped_existing"] == 0
