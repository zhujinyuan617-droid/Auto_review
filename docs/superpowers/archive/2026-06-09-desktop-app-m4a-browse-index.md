# Desktop App M4a — Browse index (SQLite) + library/detail/network endpoints

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the library queryable for browsing: a rebuildable SQLite index over the per-paper `literature_card.json` artifacts, plus read endpoints — `GET /library/papers` (rich list), `GET /papers/{id}` (one paper's card), `GET /network` (the typed relation graph read from the engine's `edges.json`).

**Architecture:** The engine JSON stays the source of truth (per repo CLAUDE.md). `store/sqlite_index.py` SCANS the library dir (each `Sxx/` subdir), reads `literature_card.json` (rich) with a `metadata_candidates.json` fallback, and writes rows into a rebuildable SQLite file (drop+recreate on reindex). `network/edges.py` reads the engine's `reports/connection/edges.json` if present (returns empty graph otherwise). API endpoints reindex-then-query (always fresh; the dataset is a few hundred papers) and expose the data. Research-group clustering is M4b (needs author data from the discovery layer, which the extraction artifacts lack).

**Tech Stack:** Python 3.12 (`desktop_app/.venv`), stdlib `sqlite3`/`json`, FastAPI, pytest. No new deps.

**Git:** branch `feat/desktop-app-m4a`; commit per task; no push; user merges after review.

**Depends on:** M1 (app, `library_index.list_papers`), M2 (cards on disk). Run from `desktop_app/` with `.venv\Scripts\python`.

---

## Verified facts (from source/artifacts — do not re-derive)

- `literature_card.json` (slim, schema 0.2.0): `{schema_version, paper_id, paper:{title,doi,year,journal,paper_type}, classification:{research_objects[],methods[],domain_tags[],gas_systems[],scale[]}, summary:{objective,main_findings[],methods_systems}, ai_warnings[]}`. NO authors.
- `metadata_candidates.json`: `{schema_version, paper_id, metadata_candidates:{title,doi,year,journal,docling_name,first_page_text}}`. NO authors.
- The desktop app's own library (built by M2a `build_clean_package`) does NOT have a `library/index.json` (that is only written by the engine's CLI scripts). So the index must SCAN subdirs, not rely on `index.json`.
- `library_index.list_papers(library_dir)` (M1) returns sorted `Sxx` subdir names.
- The engine relation network is a stable artifact: `Document_Decomposer/reports/connection/edges.json` with `{model, n_edges, relation_counts, edges:[{a,b,relation,direction,shared:{topic,method,object},candidate_score,rationale,model}]}`. It is keyed by engine paper ids; it may be absent (the desktop app's own imported papers won't have edges until the connection layer runs — out of scope here). The network endpoint must tolerate a missing file.

---

## File Structure (all under `desktop_app/`)

- `src/autoreview_app/store/__init__.py`
- `src/autoreview_app/store/sqlite_index.py` — `reindex(library_dir, db_path)`, `query_papers(db_path)`, `get_paper(db_path, paper_id)`
- `src/autoreview_app/network/__init__.py`
- `src/autoreview_app/network/edges.py` — `load_edges(edges_path)`
- `src/autoreview_app/api.py` — MODIFY: `GET /library/papers`, `GET /papers/{paper_id}`, `GET /network`
- Tests: `tests/test_sqlite_index.py`, `tests/test_edges.py`, `tests/test_api_browse.py`, plus a `tests/_library_fixtures.py` helper

Boundaries: `store` owns the index (sqlite + json reading); `network` owns edge loading; `api` wires HTTP. Each testable with temp library fixtures (no engine run needed).

---

### Task 1: SQLite browse index

**Files:**
- Create: `desktop_app/src/autoreview_app/store/__init__.py`
- Create: `desktop_app/src/autoreview_app/store/sqlite_index.py`
- Create: `desktop_app/tests/_library_fixtures.py`
- Test: `desktop_app/tests/test_sqlite_index.py`

- [ ] **Step 1: Create the library fixture helper** — `desktop_app/tests/_library_fixtures.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


def write_card(library: Path, paper_id: str, *, title: str, year: str = "2020",
               journal: str = "Fuel", doi: str = "", tags: list[str] | None = None,
               findings: list[str] | None = None) -> None:
    """Write a minimal slim literature_card.json for one paper under library/<id>/."""
    paper_dir = library / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    card = {
        "schema_version": "0.2.0",
        "paper_id": paper_id,
        "paper": {"title": title, "doi": doi, "year": year, "journal": journal, "paper_type": "article"},
        "classification": {
            "research_objects": tags or [], "methods": [], "domain_tags": [],
            "gas_systems": [], "scale": [],
        },
        "summary": {"objective": f"Study {title}", "main_findings": findings or ["A finding."], "methods_systems": ""},
        "ai_warnings": [],
    }
    (paper_dir / "literature_card.json").write_text(json.dumps(card), encoding="utf-8")
```

- [ ] **Step 2: Write the failing tests** — `desktop_app/tests/test_sqlite_index.py`:

```python
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
    # add a paper, reindex again — count reflects the new state, no duplicates
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
```

- [ ] **Step 3: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_sqlite_index.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.store'`.

- [ ] **Step 4: Implement** — `desktop_app/src/autoreview_app/store/__init__.py`:

```python
"""Rebuildable SQLite browse index over the engine's per-paper card JSON."""
```

`desktop_app/src/autoreview_app/store/sqlite_index.py`:

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from ..library_index import list_papers

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
    """(Re)build the SQLite index from the library dir. Returns the paper count."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DROP TABLE IF EXISTS papers")
        conn.execute(
            """
            CREATE TABLE papers (
                paper_id TEXT PRIMARY KEY, has_card INTEGER,
                title TEXT, year TEXT, journal TEXT, doi TEXT, paper_type TEXT,
                objective TEXT, research_objects TEXT, methods TEXT,
                domain_tags TEXT, main_findings TEXT
            )
            """
        )
        rows = [_row_from(pid, _load_card(library_dir / pid)) for pid in list_papers(library_dir)]
        conn.executemany(
            """
            INSERT INTO papers VALUES
            (:paper_id, :has_card, :title, :year, :journal, :doi, :paper_type,
             :objective, :research_objects, :methods, :domain_tags, :main_findings)
            """,
            rows,
        )
        conn.commit()
        return len(rows)
    finally:
        conn.close()


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
```

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_sqlite_index.py -v
```

Expected: PASS (4 passed).

- [ ] **Step 6: Commit.**

```powershell
git checkout -b feat/desktop-app-m4a
git add desktop_app/src/autoreview_app/store/__init__.py desktop_app/src/autoreview_app/store/sqlite_index.py desktop_app/tests/_library_fixtures.py desktop_app/tests/test_sqlite_index.py
git commit -m "feat(desktop): rebuildable SQLite browse index over card JSON"
```

---

### Task 2: Relation-network edge loader

**Files:**
- Create: `desktop_app/src/autoreview_app/network/__init__.py`
- Create: `desktop_app/src/autoreview_app/network/edges.py`
- Test: `desktop_app/tests/test_edges.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_edges.py`:

```python
import json
from pathlib import Path

from autoreview_app.network.edges import load_edges


def test_missing_file_returns_empty_graph(tmp_path: Path):
    graph = load_edges(tmp_path / "nope.json")
    assert graph == {"edges": [], "relation_counts": {}, "n_edges": 0}


def test_loads_edges_and_counts(tmp_path: Path):
    path = tmp_path / "edges.json"
    path.write_text(json.dumps({
        "relation_counts": {"supports": 1, "contradicts": 1},
        "edges": [
            {"a": "S1", "b": "S2", "relation": "supports", "rationale": "x"},
            {"a": "S2", "b": "S3", "relation": "contradicts", "rationale": "y"},
        ],
    }), encoding="utf-8")

    graph = load_edges(path)
    assert graph["n_edges"] == 2
    assert graph["relation_counts"] == {"supports": 1, "contradicts": 1}
    assert graph["edges"][0]["a"] == "S1"


def test_malformed_file_returns_empty_graph(tmp_path: Path):
    path = tmp_path / "edges.json"
    path.write_text("not json", encoding="utf-8")
    assert load_edges(path) == {"edges": [], "relation_counts": {}, "n_edges": 0}
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_edges.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.network'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/network/__init__.py`:

```python
"""Relation network: read the engine's typed edges.json for the network view."""
```

`desktop_app/src/autoreview_app/network/edges.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_EMPTY: dict[str, Any] = {"edges": [], "relation_counts": {}, "n_edges": 0}


def load_edges(edges_path: Path) -> dict[str, Any]:
    """Read the engine's edges.json. Returns an empty graph if missing/malformed.

    The connection layer may not have run for the current library; the network
    view must degrade gracefully rather than error.
    """
    if not edges_path.is_file():
        return dict(_EMPTY)
    try:
        data = json.loads(edges_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(_EMPTY)
    edges = data.get("edges") or []
    return {
        "edges": edges,
        "relation_counts": data.get("relation_counts") or {},
        "n_edges": len(edges),
    }
```

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_edges.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/network/__init__.py desktop_app/src/autoreview_app/network/edges.py desktop_app/tests/test_edges.py
git commit -m "feat(desktop): edges.json loader with graceful empty/malformed handling"
```

---

### Task 3: Browse API routes (library/papers, papers/{id}, network)

**Files:**
- Modify: `desktop_app/src/autoreview_app/api.py`
- Modify: `desktop_app/src/autoreview_app/config.py`
- Test: `desktop_app/tests/test_api_browse.py`

`AppConfig` gains two derived paths (the index db + the engine edges file) so the routes know where to read/write. Browse routes reindex-then-query (always fresh).

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_api_browse.py`:

```python
import json
from pathlib import Path

from fastapi.testclient import TestClient

from _library_fixtures import write_card

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(library: Path, edges_path: Path | None = None):
    config = AppConfig(library_dir=library, edges_path=edges_path)
    return TestClient(create_app(config))


def test_library_papers_lists_indexed_cards(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="Alpha", doi="10.1/a", tags=["methane"])
    write_card(library, "S2", title="Beta")

    resp = _client(library).get("/library/papers")
    assert resp.status_code == 200
    papers = resp.json()["papers"]
    assert {p["paper_id"] for p in papers} == {"S1", "S2"}
    s1 = next(p for p in papers if p["paper_id"] == "S1")
    assert s1["title"] == "Alpha"
    assert s1["research_objects"] == ["methane"]


def test_paper_detail(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="Alpha")
    client = _client(library)
    assert client.get("/papers/S1").json()["title"] == "Alpha"
    assert client.get("/papers/missing").status_code == 404


def test_network_reads_edges(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="A")
    edges_path = tmp_path / "edges.json"
    edges_path.write_text(json.dumps({
        "relation_counts": {"supports": 1},
        "edges": [{"a": "S1", "b": "S2", "relation": "supports"}],
    }), encoding="utf-8")

    resp = _client(library, edges_path=edges_path).get("/network")
    assert resp.status_code == 200
    assert resp.json()["n_edges"] == 1


def test_network_missing_edges_is_empty(tmp_path: Path):
    library = tmp_path / "library"
    resp = _client(library, edges_path=tmp_path / "nope.json").get("/network")
    assert resp.json() == {"edges": [], "relation_counts": {}, "n_edges": 0}
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_browse.py -v
```

Expected: FAIL — `AppConfig` has no `edges_path` field (TypeError).

- [ ] **Step 3: Extend `AppConfig`.** Replace `desktop_app/src/autoreview_app/config.py` with:

```python
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_LIBRARY_DIR = "AUTOREVIEW_LIBRARY_DIR"
DEFAULT_LIBRARY_DIRNAME = "library"


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the desktop app."""

    library_dir: Path
    edges_path: Path | None = None

    @property
    def index_db(self) -> Path:
        """SQLite browse index, kept beside the library dir."""
        return self.library_dir.parent / "index.db"

    @classmethod
    def from_env(cls) -> "AppConfig":
        raw = os.environ.get(ENV_LIBRARY_DIR)
        library = Path(raw) if raw else Path.cwd() / DEFAULT_LIBRARY_DIRNAME
        return cls(library_dir=library)
```

- [ ] **Step 4: Add the routes.** In `desktop_app/src/autoreview_app/api.py`, add imports near the other local imports:

```python
from .network.edges import load_edges
from .store.sqlite_index import get_paper, query_papers, reindex
```

Inside `create_app`, before `return app`, add:

```python
    @app.get("/library/papers")
    def library_papers() -> dict:
        reindex(config.library_dir, config.index_db)
        return {"papers": query_papers(config.index_db)}

    @app.get("/papers/{paper_id}")
    def paper_detail(paper_id: str) -> dict[str, Any]:
        reindex(config.library_dir, config.index_db)
        paper = get_paper(config.index_db, paper_id)
        if paper is None:
            raise HTTPException(status_code=404, detail="unknown paper")
        return paper

    @app.get("/network")
    def network() -> dict[str, Any]:
        if config.edges_path is None:
            return {"edges": [], "relation_counts": {}, "n_edges": 0}
        return load_edges(config.edges_path)
```

(Leave existing routes unchanged.)

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_browse.py -v
```

Expected: PASS (4 passed). Then confirm no regression on existing api tests: `.venv\Scripts\python -m pytest tests/test_api.py tests/test_api_import.py tests/test_api_discovery.py -v` → 8 passed.

- [ ] **Step 6: Run the FULL suite** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -q
```

Expected: all green. Report the exact summary line.

- [ ] **Step 7: Commit.**

```powershell
git add desktop_app/src/autoreview_app/api.py desktop_app/src/autoreview_app/config.py desktop_app/tests/test_api_browse.py
git commit -m "feat(desktop): /library/papers + /papers/{id} + /network browse routes"
```

---

## Done criteria for M4a

- A rebuildable SQLite index over the library's card JSON (`reindex`/`query_papers`/`get_paper`); papers without a card are still listed.
- `load_edges` reads the engine's `edges.json` and degrades to an empty graph if missing/malformed.
- API: `GET /library/papers` (rich list), `GET /papers/{id}` (404 for unknown), `GET /network`.
- Full suite green. Branch `feat/desktop-app-m4a`; not pushed.

## Out of scope for M4a (next)

- **M4b research-group clustering** — needs author/identity data captured from the discovery layer (Crossref/RIS) keyed by DOI (the extraction artifacts have no authors). That is its own milestone (anchor = corresponding/last author, identity = ORCID > name+affiliation, plus co-authorship community).
- Real frontend screens (library grid, interactive network graph) — the backend endpoints land here; the visual UI is a dedicated frontend pass.
- Generating `edges.json` for the desktop app's own imported papers (running the connection layer) — separate.
- Wiring a persistent reindex trigger / incremental index — M4a reindexes per request (fine for hundreds of papers).

---

## Self-review (planner)

- **Coverage vs roadmap M4 (browse half):** SQLite index (Task 1), network read (Task 2), browse/detail/network endpoints (Task 3). Research-group clustering split to M4b (grounded reason: no author data in extraction artifacts). Frontend screens deferred to a frontend pass. ✓
- **Placeholders:** none — full code/commands per step. ✓
- **Type/name consistency:** `reindex(library_dir, db_path)`, `query_papers(db_path)`, `get_paper(db_path, paper_id)` defined Task 1, used Task 3. `load_edges(edges_path)` Task 2, used Task 3. `AppConfig(library_dir, edges_path=None)` + `.index_db` property (Task 3) — additive; existing callers pass only `library_dir` and keep working (`from_env` unchanged in behavior). `create_app(config, import_runner=None, search_runner=None)` unchanged signature. ✓
