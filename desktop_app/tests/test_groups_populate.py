import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _library_fixtures
from _library_fixtures import write_card

from autoreview_app.groups.populate import populate_authors
from autoreview_app.groups.store import load_authors
from autoreview_app.discovery.records import CitationRecord


def test_populate_fills_author_store(tmp_path):
    lib = tmp_path / "library"
    write_card(lib, "S01", title="A", doi="10.1/aaa")
    write_card(lib, "S02", title="B", doi="10.2/bbb")
    write_card(lib, "S03", title="C", doi="")  # blank doi -> skipped

    canned = {
        "10.1/aaa": CitationRecord(title="A", doi="10.1/aaa", year="2020", journal="J", authors=("Yin, X", "Koch, D")),
        "10.2/bbb": CitationRecord(title="B", doi="10.2/bbb", year="2021", journal="J", authors=("Jin, Z",)),
    }
    db = tmp_path / "authors.db"
    counts = populate_authors(lib, db, lambda doi: canned.get(doi))
    assert counts["found"] == 2
    assert counts["skipped"] == 1
    by_doi = load_authors(db)
    assert by_doi["10.1/aaa"] == ["Yin, X", "Koch, D"]
    assert by_doi["10.2/bbb"] == ["Jin, Z"]
