from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..library_index import list_papers
from .store import save_authors


def _doi_of(paper_dir: Path) -> str:
    card_path = paper_dir / "literature_card.json"
    if not card_path.is_file():
        return ""
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return ((card.get("paper") or {}).get("doi") or "").strip()


def populate_authors(
    library_dir: Path,
    authors_db: Path,
    fetch_author: Callable[[str], Any],
    progress: Callable[[str], None] = lambda _m: None,
) -> dict[str, int]:
    """Populate the author store: for each paper's DOI, look up authors via
    fetch_author(doi) -> CitationRecord|None, and save_authors(db, doi, [names]).
    Papers with blank DOI or no author hit are skipped. Returns {found, skipped}."""
    ids = list_papers(library_dir)
    found = skipped = 0
    for i, pid in enumerate(ids):
        progress(f"{i + 1}/{len(ids)} {pid}")
        doi = _doi_of(library_dir / pid)
        if not doi:
            skipped += 1
            continue
        try:
            rec = fetch_author(doi)
        except Exception:  # noqa: BLE001 — network hiccup; skip this paper
            rec = None
        authors = list(rec.authors) if rec and rec.authors else []
        if not authors:
            skipped += 1
            continue
        save_authors(authors_db, doi, authors)
        found += 1
    return {"found": found, "skipped": skipped}
