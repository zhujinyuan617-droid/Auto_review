from pathlib import Path

from autoreview_app.library_index import list_papers


def test_missing_dir_returns_empty(tmp_path: Path):
    assert list_papers(tmp_path / "does_not_exist") == []


def test_empty_dir_returns_empty(tmp_path: Path):
    assert list_papers(tmp_path) == []


def test_lists_paper_subdirs_sorted_ignoring_files_and_hidden(tmp_path: Path):
    (tmp_path / "S02").mkdir()
    (tmp_path / "S01").mkdir()
    (tmp_path / ".cache").mkdir()
    (tmp_path / "index.json").write_text("{}", encoding="utf-8")

    assert list_papers(tmp_path) == ["S01", "S02"]
