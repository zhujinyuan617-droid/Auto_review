from pathlib import Path

from autoreview_app.groups.store import load_authors, save_authors


def test_save_and_load(tmp_path: Path):
    db = tmp_path / "authors.db"
    save_authors(db, "10.1/a", ["First, A", "Senior, C"])
    save_authors(db, "10.1/b", ["Solo, S"])
    authors = load_authors(db)
    assert authors == {"10.1/a": ["First, A", "Senior, C"], "10.1/b": ["Solo, S"]}


def test_save_is_idempotent_upsert(tmp_path: Path):
    db = tmp_path / "authors.db"
    save_authors(db, "10.1/a", ["Old, O"])
    save_authors(db, "10.1/a", ["New, N", "Senior, C"])  # same DOI -> replace
    assert load_authors(db)["10.1/a"] == ["New, N", "Senior, C"]


def test_blank_doi_is_ignored(tmp_path: Path):
    db = tmp_path / "authors.db"
    save_authors(db, "", ["X, Y"])
    assert load_authors(db) == {}


def test_load_missing_db_is_empty(tmp_path: Path):
    assert load_authors(tmp_path / "nope.db") == {}
