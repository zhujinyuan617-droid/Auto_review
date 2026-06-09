from autoreview_app.groups.cluster import cluster_papers


def test_groups_papers_by_senior_author():
    papers = [
        {"paper_id": "S1", "doi": "10.1/a", "title": "A"},
        {"paper_id": "S2", "doi": "10.1/b", "title": "B"},
        {"paper_id": "S3", "doi": "10.1/c", "title": "C"},
    ]
    authors_by_doi = {
        "10.1/a": ["Junior, X", "Lee, Min"],
        "10.1/b": ["Other, Y", "Lee, M."],   # same senior (Lee, M) -> same group
        "10.1/c": ["Solo, Z", "Brown, Bob"],
    }
    groups = cluster_papers(papers, authors_by_doi)

    by_anchor = {g["anchor_identity"]: g for g in groups}
    assert set(by_anchor) == {"lee_m", "brown_b"}
    lee = by_anchor["lee_m"]
    assert {p["paper_id"] for p in lee["papers"]} == {"S1", "S2"}
    assert lee["size"] == 2
    assert lee["evidence"] == "senior_author_name"


def test_paper_without_authors_is_ungrouped():
    papers = [{"paper_id": "S1", "doi": "10.1/x", "title": "X"}]
    groups = cluster_papers(papers, authors_by_doi={})
    assert groups == []


def test_singletons_are_groups_too():
    papers = [{"paper_id": "S1", "doi": "10.1/a", "title": "A"}]
    groups = cluster_papers(papers, {"10.1/a": ["Solo, S"]})
    assert len(groups) == 1
    assert groups[0]["size"] == 1
