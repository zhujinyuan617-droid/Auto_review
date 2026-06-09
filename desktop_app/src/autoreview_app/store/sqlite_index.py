from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from ..library_index import list_papers

# FastAPI runs sync route handlers in a threadpool, so reindex can be called
# concurrently. Serialize writers so two threads never race on the rebuild.
_REINDEX_LOCK = threading.Lock()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS papers (
    paper_id TEXT PRIMARY KEY, has_card INTEGER,
    title TEXT, year TEXT, journal TEXT, doi TEXT, paper_type TEXT,
    objective TEXT, research_objects TEXT, methods TEXT,
    domain_tags TEXT, main_findings TEXT
)
"""

# Columns kept as JSON text (tag arrays / findings) are decoded on read.
_JSON_COLS = ("research_objects", "methods", "domain_tags", "main_findings")


def _load_card(paper_dir: Path) -> dict[str, Any] | None:
    card_path = paper_dir / "literature_card.json"
    if not card_path.is_file():
        return None
    try:
        return json.loads(card_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _row_from(paper_id: str, card: dict[str, Any] | None) -> dict[str, Any]:
    paper = (card or {}).get("paper") or {}
    classification = (card or {}).get("classification") or {}
    summary = (card or {}).get("summary") or {}
    return {
        "paper_id": paper_id,
        "has_card": 1 if card else 0,
        "title": paper.get("title", ""),
        "year": str(paper.get("year", "")),
        "journal": paper.get("journal", ""),
        "doi": paper.get("doi", ""),
        "paper_type": paper.get("paper_type", ""),
        "objective": summary.get("objective", ""),
        "research_objects": json.dumps(classification.get("research_objects") or []),
        "methods": json.dumps(classification.get("methods") or []),
        "domain_tags": json.dumps(classification.get("domain_tags") or []),
        "main_findings": json.dumps(summary.get("main_findings") or []),
    }


def reindex(library_dir: Path, db_path: Path) -> int:
    """(Re)build the SQLite index from the library dir. Returns the paper count.

    Concurrency-safe and atomic: the table is created once (never dropped), and
    the clear+reinsert happens inside one transaction under a process-wide lock.
    A concurrent reader on another connection always sees a complete table
    (old rows or new rows), never a half-dropped one.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_row_from(pid, _load_card(library_dir / pid)) for pid in list_papers(library_dir)]
    with _REINDEX_LOCK:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(_CREATE_TABLE)
            with conn:  # one transaction: DELETE + re-INSERT commit together
                conn.execute("DELETE FROM papers")
                conn.executemany(
                    """
                    INSERT INTO papers VALUES
                    (:paper_id, :has_card, :title, :year, :journal, :doi, :paper_type,
                     :objective, :research_objects, :methods, :domain_tags, :main_findings)
                    """,
                    rows,
                )
        finally:
            conn.close()
    return len(rows)


def _decode(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["has_card"] = bool(item["has_card"])
    for col in _JSON_COLS:
        item[col] = json.loads(item[col]) if item.get(col) else []
    return item


def query_papers(db_path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM papers ORDER BY paper_id").fetchall()
        return [_decode(r) for r in rows]
    finally:
        conn.close()


def get_paper(db_path: Path, paper_id: str) -> dict[str, Any] | None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute("SELECT * FROM papers WHERE paper_id = ?", (paper_id,)).fetchone()
        return _decode(row) if row is not None else None
    finally:
        conn.close()
