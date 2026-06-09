from pathlib import Path

from _library_fixtures import write_card

from autoreview_app.store.sqlite_index import get_paper, query_papers, reindex


def test_reindex_counts_and_queries(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="Methane Adsorption", year="2020", doi="10.1/a", tags=["methane"])
    write_card(library, "S2", title="Carbon Capture", year="2019", doi="10.1/b")
    db = tmp_path / "index.db"

    n = reindex(library, db)
    assert n == 2

    papers = query_papers(db)
    ids = {p["paper_id"] for p in papers}
    assert ids == {"S1", "S2"}
    s1 = next(p for p in papers if p["paper_id"] == "S1")
    assert s1["title"] == "Methane Adsorption"
    assert s1["year"] == "2020"
    assert s1["doi"] == "10.1/a"
    assert s1["research_objects"] == ["methane"]


def test_get_paper_returns_full_card(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="T", findings=["f1", "f2"])
    db = tmp_path / "index.db"
    reindex(library, db)

    paper = get_paper(db, "S1")
    assert paper is not None
    assert paper["title"] == "T"
    assert paper["main_findings"] == ["f1", "f2"]
    assert get_paper(db, "missing") is None


def test_reindex_is_rebuildable(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="One")
    db = tmp_path / "index.db"
    reindex(library, db)
    write_card(library, "S2", title="Two")
    n = reindex(library, db)
    assert n == 2
    assert len(query_papers(db)) == 2


def test_paper_without_card_is_indexed_minimally(tmp_path: Path):
    library = tmp_path / "library"
    (library / "S9").mkdir(parents=True)  # no literature_card.json
    db = tmp_path / "index.db"
    n = reindex(library, db)
    assert n == 1
    s9 = query_papers(db)[0]
    assert s9["paper_id"] == "S9"
    assert s9["has_card"] is False
