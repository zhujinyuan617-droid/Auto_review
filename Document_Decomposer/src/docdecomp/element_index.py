"""Rebuildable SQLite index over per-paper elements.json + the registry.

Mirrors the desktop sqlite_index.py house style: CREATE IF NOT EXISTS once,
clear+reinsert in ONE transaction, short-lived connections, row_factory=Row.
Occurrences store the redirect-RESOLVED element_id, so all queries stay simple.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from .element_registry import resolve_id

_REINDEX_LOCK = threading.Lock()

_CREATE = """
CREATE TABLE IF NOT EXISTS elements (
    element_id TEXT PRIMARY KEY, facet TEXT, slug TEXT, display_name TEXT,
    aliases_json TEXT, human_locked INTEGER
);
CREATE TABLE IF NOT EXISTS occurrences (
    paper_id TEXT, element_id TEXT, facet TEXT, surface TEXT, quote TEXT,
    reading_block_id TEXT, role TEXT, digits_verified INTEGER, values_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_occ_elem ON occurrences(element_id);
CREATE INDEX IF NOT EXISTS idx_occ_paper ON occurrences(paper_id);
CREATE INDEX IF NOT EXISTS idx_occ_facet ON occurrences(facet);
"""


def _slug(element_id: str) -> str:
    return element_id.split("/", 1)[1] if "/" in element_id else element_id


def _facet_of(element_id: str) -> str:
    return element_id.split(":", 1)[1].split("/", 1)[0]


def build_index(library_dir: Path, registry: dict, db_path: Path) -> int:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    elem_rows = [
        (e["id"], e["facet"], _slug(e["id"]), e["display_name"],
         json.dumps(e.get("aliases") or [], ensure_ascii=False), int(e.get("human_locked", False)))
        for e in registry["entries"].values()
        if not e.get("redirect_to")
    ]
    occ_rows = []
    paper_ids = set()
    for elements_path in sorted(Path(library_dir).glob("*/elements.json")):
        data = json.loads(elements_path.read_text(encoding="utf-8"))
        paper_ids.add(data.get("paper_id") or elements_path.parent.name)
        for o in data.get("occurrences") or []:
            eid = o.get("canonical_id")
            if not eid:
                continue
            eid = resolve_id(registry, eid)
            occ_rows.append(
                (data.get("paper_id") or elements_path.parent.name, eid, _facet_of(eid),
                 o["surface"], o["quote"], o["reading_block_id"], o["role"],
                 int(o.get("digits_verified", False)),
                 json.dumps(o.get("values") or [], ensure_ascii=False))
            )
    with _REINDEX_LOCK:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA busy_timeout=5000")  # explicit: readers must wait out a rebuild transaction instead of raising "database is locked"
        try:
            conn.executescript(_CREATE)
            with conn:
                conn.execute("DELETE FROM elements")
                conn.execute("DELETE FROM occurrences")
                conn.executemany("INSERT INTO elements VALUES (?,?,?,?,?,?)", elem_rows)
                conn.executemany("INSERT INTO occurrences VALUES (?,?,?,?,?,?,?,?,?)", occ_rows)
        finally:
            conn.close()
    return len(paper_ids)


def _conn(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout=5000")
    conn.row_factory = sqlite3.Row
    return conn


def _role_clause(role: str | None) -> tuple[str, list]:
    return ("AND o.role = ?", [role]) if role else ("", [])


def query_stats(db_path: Path, facet: str, role: str | None = "used") -> list[dict]:
    clause, args = _role_clause(role)
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            f"""SELECT e.element_id AS id, e.slug, e.display_name,
                       COUNT(DISTINCT o.paper_id) AS papers
                FROM elements e JOIN occurrences o ON o.element_id = e.element_id
                WHERE e.facet = ? {clause}
                GROUP BY e.element_id ORDER BY papers DESC, e.display_name""",
            [facet, *args],
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def query_overview(db_path: Path, top_n: int = 5, role: str | None = "used") -> dict:
    conn = _conn(db_path)
    try:
        facets = [r["facet"] for r in conn.execute(
            "SELECT DISTINCT facet FROM elements ORDER BY facet").fetchall()]
        total_papers = conn.execute(
            "SELECT COUNT(DISTINCT paper_id) AS n FROM occurrences").fetchone()["n"]
    finally:
        conn.close()
    out = {"library_papers": total_papers, "facets": []}
    for facet in facets:
        items = query_stats(db_path, facet, role)
        out["facets"].append({"id": facet, "total_elements": len(items), "top": items[:top_n]})
    return out


def search_elements(db_path: Path, q: str, facet: str | None = None) -> list[dict]:
    like = f"%{q.lower()}%"
    conn = _conn(db_path)
    try:
        facet_clause = "AND e.facet = ?" if facet else ""
        args = [like, like] + ([facet] if facet else [])
        rows = conn.execute(
            f"""SELECT e.element_id AS id, e.facet, e.slug, e.display_name, e.aliases_json,
                       (SELECT COUNT(DISTINCT o.paper_id) FROM occurrences o
                        WHERE o.element_id = e.element_id AND o.role = 'used') AS papers
                FROM elements e
                WHERE (LOWER(e.display_name) LIKE ? OR LOWER(e.aliases_json) LIKE ?) {facet_clause}
                ORDER BY papers DESC LIMIT 50""",
            args,
        ).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            item["aliases"] = json.loads(item.pop("aliases_json"))
            out.append(item)
        return out
    finally:
        conn.close()


def get_element(db_path: Path, facet: str, slug: str, role: str | None = "used") -> dict | None:
    conn = _conn(db_path)
    try:
        e = conn.execute(
            "SELECT * FROM elements WHERE facet = ? AND slug = ?", (facet, slug)
        ).fetchone()
        if e is None:
            return None
        clause, args = _role_clause(role)
        occ = conn.execute(
            f"SELECT * FROM occurrences o WHERE o.element_id = ? {clause} ORDER BY paper_id",
            [e["element_id"], *args],
        ).fetchall()
    finally:
        conn.close()
    papers: dict[str, list] = {}
    for o in occ:
        papers.setdefault(o["paper_id"], []).append(
            {"surface": o["surface"], "quote": o["quote"], "reading_block_id": o["reading_block_id"],
             "role": o["role"], "values": json.loads(o["values_json"])}
        )
    return {
        "id": e["element_id"], "facet": e["facet"], "slug": e["slug"],
        "display_name": e["display_name"], "aliases": json.loads(e["aliases_json"]),
        "human_locked": bool(e["human_locked"]),
        "paper_count": len(papers),
        "papers": [{"paper_id": pid, "quotes": qs} for pid, qs in sorted(papers.items())],
    }


def query_cooccurrence(db_path: Path, facet: str, slug: str, role: str = "used") -> dict:
    conn = _conn(db_path)
    try:
        e = conn.execute(
            "SELECT element_id FROM elements WHERE facet = ? AND slug = ?", (facet, slug)
        ).fetchone()
        if e is None:
            return {"anchor": None, "m": 0, "groups": []}
        anchor = e["element_id"]
        rows = conn.execute(
            """SELECT o.facet, o.element_id AS id, e.display_name,
                      COUNT(DISTINCT o.paper_id) AS n
               FROM occurrences o JOIN elements e ON e.element_id = o.element_id
               WHERE o.role = ? AND o.element_id != ?
                 AND o.paper_id IN (SELECT DISTINCT paper_id FROM occurrences
                                    WHERE element_id = ? AND role = ?)
               GROUP BY o.element_id ORDER BY n DESC""",
            (role, anchor, anchor, role),
        ).fetchall()
        m = conn.execute(
            "SELECT COUNT(DISTINCT paper_id) AS n FROM occurrences WHERE element_id = ? AND role = ?",
            (anchor, role),
        ).fetchone()["n"]
    finally:
        conn.close()
    groups: dict[str, list] = {}
    for r in rows:
        groups.setdefault(r["facet"], []).append(
            {"id": r["id"], "display_name": r["display_name"], "n": r["n"]}
        )
    return {"anchor": anchor, "m": m,
            "groups": [{"facet": f, "items": items} for f, items in sorted(groups.items())]}


def query_combination(db_path: Path, element_ids: list[str], role: str = "used") -> dict:
    if not element_ids:
        return {"papers": []}
    placeholders = ",".join("?" for _ in element_ids)
    conn = _conn(db_path)
    try:
        pids = [r["paper_id"] for r in conn.execute(
            f"""SELECT paper_id FROM occurrences
                WHERE element_id IN ({placeholders}) AND role = ?
                GROUP BY paper_id
                HAVING COUNT(DISTINCT element_id) = ?
                ORDER BY paper_id""",
            [*element_ids, role, len(element_ids)],
        ).fetchall()]
        papers = []
        for pid in pids:
            occ = conn.execute(
                f"""SELECT o.*, e.display_name FROM occurrences o
                    JOIN elements e ON e.element_id = o.element_id
                    WHERE o.paper_id = ? AND o.element_id IN ({placeholders}) AND o.role = ?""",
                [pid, *element_ids, role],
            ).fetchall()
            papers.append({
                "paper_id": pid,
                "matches": [{"element_id": o["element_id"], "display_name": o["display_name"],
                             "surface": o["surface"], "quote": o["quote"],
                             "reading_block_id": o["reading_block_id"],
                             "values": json.loads(o["values_json"])} for o in occ],
            })
    finally:
        conn.close()
    return {"papers": papers}


def paper_elements(db_path: Path, paper_id: str) -> dict:
    """All occurrences for one paper, grouped by facet. Deliberately unfiltered by
    role (a paper detail view wants everything); each item carries its role."""
    conn = _conn(db_path)
    try:
        rows = conn.execute(
            """SELECT o.*, e.display_name FROM occurrences o
               JOIN elements e ON e.element_id = o.element_id
               WHERE o.paper_id = ? ORDER BY o.facet, e.display_name""",
            (paper_id,),
        ).fetchall()
    finally:
        conn.close()
    groups: dict[str, list] = {}
    for o in rows:
        groups.setdefault(o["facet"], []).append(
            {"element_id": o["element_id"], "display_name": o["display_name"],
             "surface": o["surface"], "quote": o["quote"], "role": o["role"],
             "reading_block_id": o["reading_block_id"], "values": json.loads(o["values_json"])}
        )
    return {"paper_id": paper_id,
            "groups": [{"facet": f, "items": items} for f, items in sorted(groups.items())]}
