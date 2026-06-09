from __future__ import annotations

from typing import Any

from .identity import anchor_author, author_identity


def cluster_papers(
    papers: list[dict[str, Any]],
    authors_by_doi: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """Group papers by their senior author's identity (the "A" primary signal).

    `papers`: each a dict with at least paper_id, doi, title.
    `authors_by_doi`: doi (lowercased) -> author list (senior author last).
    Returns one group per distinct senior-author identity, each with its papers,
    the anchor display name, the identity key, a size, and the grouping evidence.
    Papers with no resolvable author identity are left ungrouped.
    """
    groups: dict[str, dict[str, Any]] = {}
    for paper in papers:
        doi = (paper.get("doi") or "").strip().lower()
        authors = authors_by_doi.get(doi) or []
        anchor = anchor_author(authors)
        identity = author_identity(anchor)
        if not identity:
            continue
        group = groups.setdefault(
            identity,
            {
                "anchor_identity": identity,
                "anchor_name": anchor,
                "papers": [],
                "size": 0,
                "evidence": "senior_author_name",
            },
        )
        group["papers"].append({"paper_id": paper.get("paper_id"), "title": paper.get("title"), "doi": doi})
        group["size"] = len(group["papers"])
    return sorted(groups.values(), key=lambda g: g["anchor_identity"])
