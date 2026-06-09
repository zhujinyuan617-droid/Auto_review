from pathlib import Path

from autoreview_app.paper_ids import allocate_paper_id


def test_empty_or_missing_library_starts_at_s1(tmp_path: Path):
    assert allocate_paper_id(tmp_path) == "S1"
    assert allocate_paper_id(tmp_path / "nope") == "S1"


def test_next_after_max_existing(tmp_path: Path):
    (tmp_path / "S05").mkdir()
    (tmp_path / "S290").mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".cache").mkdir()
    assert allocate_paper_id(tmp_path) == "S291"


def test_ignores_non_matching_dir_names(tmp_path: Path):
    (tmp_path / "S12").mkdir()
    (tmp_path / "Sxx").mkdir()
    (tmp_path / "S12abc").mkdir()
    assert allocate_paper_id(tmp_path) == "S13"
