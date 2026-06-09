from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

_LOCK = threading.Lock()
_CREATE = "CREATE TABLE IF NOT EXISTS authors (doi TEXT PRIMARY KEY, authors TEXT)"


def save_authors(db_path: Path, doi: str, authors: list[str]) -> None:
    """Upsert the author list for a DOI (keyed by DOI). Blank DOI is ignored."""
    doi = (doi or "").strip().lower()
    if not doi:
        return
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(_CREATE)
            with conn:
                conn.execute(
                    "INSERT INTO authors (doi, authors) VALUES (?, ?) "
                    "ON CONFLICT(doi) DO UPDATE SET authors = excluded.authors",
                    (doi, json.dumps(list(authors))),
                )
        finally:
            conn.close()


def load_authors(db_path: Path) -> dict[str, list[str]]:
    """Return {doi -> [author, ...]}. Empty dict if the store doesn't exist yet."""
    if not db_path.is_file():
        return {}
    conn = sqlite3.connect(db_path)
    try:
        try:
            rows = conn.execute("SELECT doi, authors FROM authors").fetchall()
        except sqlite3.OperationalError:
            return {}
        return {doi: json.loads(authors) for doi, authors in rows}
    finally:
        conn.close()
