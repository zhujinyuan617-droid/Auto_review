# Desktop App M4b — Research-group clustering (PI/senior-author)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Group papers that come from the same research group, keyed on the senior (PI) author's identity. Because the extraction artifacts have NO authors, the author data comes from the discovery layer (`CitationRecord`, populated by Crossref/RIS). A DOI-keyed author store persists that data; a deterministic clusterer groups papers by senior-author identity; a `GET /groups` endpoint exposes the groups.

**Architecture:** Pure, deterministic, offline. `groups/identity.py` normalizes an author name (and prefers a stable id when present) into an identity key. `groups/store.py` persists `doi -> [authors]` (SQLite, rebuildable). `groups/cluster.py` takes papers (each with a DOI + the library card's title/year) plus the author store, picks each paper's **anchor** (senior author = last author by default), resolves its identity, and groups papers sharing an anchor identity; each group carries its member papers + the evidence (which signal grouped them) + a confidence. `api.py` adds `GET /groups`. Co-authorship community (the "C" auxiliary signal) is noted as a follow-up; M4b ships the "A" primary path (senior-author identity), which is the dominant signal.

**Tech Stack:** Python 3.12 (`desktop_app/.venv`), stdlib `sqlite3`/`json`/`re`, FastAPI, pytest. No new deps, no network in tests.

**Git:** branch `feat/desktop-app-m4b`; commit per task; no push; user merges after review.

**Depends on:** M3 (`CitationRecord`), M4a (the browse index / library). Run from `desktop_app/` with `.venv\Scripts\python`.

---

## Verified facts (do not re-derive)

- Extraction artifacts (`literature_card.json`, `metadata_candidates.json`) have NO authors. Author data exists only in `discovery/records.py CitationRecord.authors: tuple[str, ...]` (from Crossref `"family, given"` or RIS `AU`).
- `CitationRecord.key` = lowercased DOI if present else lowercased title. DOI is the join key between discovery records and library papers.
- M4a `store/sqlite_index.py` already indexes the library cards (paper_id, title, year, journal, doi, ...). M4b joins on `doi`.
- The real discovery→download→import wiring that would populate the author store at runtime was deferred in M3; M4b's store is populated by whatever path has the records (tests populate it directly; a future task wires it to the download flow).

---

## File Structure (all under `desktop_app/`)

- `src/autoreview_app/groups/__init__.py`
- `src/autoreview_app/groups/identity.py` — `author_identity(name)`, `anchor_author(authors)`
- `src/autoreview_app/groups/store.py` — `save_authors(db_path, doi, authors)`, `load_authors(db_path) -> dict[str, list[str]]`
- `src/autoreview_app/groups/cluster.py` — `cluster_papers(papers, authors_by_doi) -> list[dict]`
- `src/autoreview_app/api.py` — MODIFY: `GET /groups`
- `src/autoreview_app/config.py` — MODIFY: add an `authors_db` property
- Tests: `tests/test_group_identity.py`, `tests/test_group_store.py`, `tests/test_group_cluster.py`, `tests/test_api_groups.py`

Boundaries: `identity` pure string logic; `store` owns persistence; `cluster` pure grouping; `api` wires. All testable offline.

---

### Task 1: Author identity + anchor selection

**Files:**
- Create: `desktop_app/src/autoreview_app/groups/__init__.py`
- Create: `desktop_app/src/autoreview_app/groups/identity.py`
- Test: `desktop_app/tests/test_group_identity.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_group_identity.py`:

```python
from autoreview_app.groups.identity import anchor_author, author_identity


def test_identity_normalizes_name():
    # Case, punctuation, and "family, given" vs "given family" normalize the same.
    assert author_identity("Smith, John") == author_identity("john  smith")
    assert author_identity("Smith, J.") == author_identity("J Smith")


def test_identity_is_family_plus_first_initial():
    # "Smith, John A." -> family "smith" + initial "j"
    assert author_identity("Smith, John A.") == "smith_j"
    assert author_identity("Wang, Li") == "wang_l"


def test_empty_identity():
    assert author_identity("") == ""
    assert author_identity("   ") == ""


def test_anchor_is_last_author():
    assert anchor_author(["First, A", "Middle, B", "Senior, C"]) == "Senior, C"


def test_anchor_empty_list():
    assert anchor_author([]) == ""
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_group_identity.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.groups'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/groups/__init__.py`:

```python
"""Research-group clustering: group papers by senior-author identity."""
```

`desktop_app/src/autoreview_app/groups/identity.py`:

```python
from __future__ import annotations

import re


def _parts(name: str) -> tuple[str, str]:
    """Return (family, given) from 'Family, Given' or 'Given Family'."""
    name = re.sub(r"\s+", " ", name).strip()
    if not name:
        return "", ""
    if "," in name:
        family, _, given = name.partition(",")
        return family.strip(), given.strip()
    tokens = name.split(" ")
    if len(tokens) == 1:
        return tokens[0], ""
    return tokens[-1], " ".join(tokens[:-1])


def author_identity(name: str) -> str:
    """A coarse identity key: lowercased family name + first given initial.

    Coarse on purpose — it merges 'Smith, John' / 'J Smith' / 'Smith, J.'.
    A stronger key (ORCID/OpenAlex id) would be preferred when available; this
    is the name-only fallback. Returns "" for an empty/blank name.
    """
    family, given = _parts(name)
    family_key = re.sub(r"[^a-z]", "", family.lower())
    if not family_key:
        return ""
    initial = ""
    given = given.strip()
    if given:
        first_alpha = re.sub(r"[^a-z]", "", given.lower())
        initial = first_alpha[:1]
    return f"{family_key}_{initial}" if initial else family_key


def anchor_author(authors: list[str]) -> str:
    """The senior author used as the group anchor. Default: the last author."""
    return authors[-1] if authors else ""
```

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_group_identity.py -v
```

Expected: PASS (5 passed).

- [ ] **Step 5: Commit.**

```powershell
git checkout -b feat/desktop-app-m4b
git add desktop_app/src/autoreview_app/groups/__init__.py desktop_app/src/autoreview_app/groups/identity.py desktop_app/tests/test_group_identity.py
git commit -m "feat(desktop): author identity key + senior-author anchor"
```

---

### Task 2: DOI-keyed author store

**Files:**
- Create: `desktop_app/src/autoreview_app/groups/store.py`
- Test: `desktop_app/tests/test_group_store.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_group_store.py`:

```python
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
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_group_store.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.groups.store'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/groups/store.py`:

```python
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
```

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_group_store.py -v
```

Expected: PASS (4 passed).

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/groups/store.py desktop_app/tests/test_group_store.py
git commit -m "feat(desktop): DOI-keyed author store (upsert, rebuildable)"
```

---

### Task 3: Cluster papers by senior-author identity

**Files:**
- Create: `desktop_app/src/autoreview_app/groups/cluster.py`
- Test: `desktop_app/tests/test_group_cluster.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_group_cluster.py`:

```python
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
    # No author data -> no group (not an error).
    assert groups == []


def test_singletons_are_groups_too():
    papers = [{"paper_id": "S1", "doi": "10.1/a", "title": "A"}]
    groups = cluster_papers(papers, {"10.1/a": ["Solo, S"]})
    assert len(groups) == 1
    assert groups[0]["size"] == 1
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_group_cluster.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.groups.cluster'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/groups/cluster.py`:

```python
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
```

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_group_cluster.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/groups/cluster.py desktop_app/tests/test_group_cluster.py
git commit -m "feat(desktop): cluster papers by senior-author identity"
```

---

### Task 4: `GET /groups` endpoint

**Files:**
- Modify: `desktop_app/src/autoreview_app/config.py`
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api_groups.py`

`AppConfig` gains an `authors_db` property. The endpoint reindexes the library, loads the author store, joins by DOI, and clusters.

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_api_groups.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from _library_fixtures import write_card

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig
from autoreview_app.groups.store import save_authors


def test_groups_endpoint_clusters_by_senior_author(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="A", doi="10.1/a")
    write_card(library, "S2", title="B", doi="10.1/b")
    config = AppConfig(library_dir=library)

    save_authors(config.authors_db, "10.1/a", ["Junior, X", "Lee, Min"])
    save_authors(config.authors_db, "10.1/b", ["Other, Y", "Lee, M."])

    client = TestClient(create_app(config))
    resp = client.get("/groups")
    assert resp.status_code == 200
    groups = resp.json()["groups"]
    assert len(groups) == 1
    g = groups[0]
    assert g["anchor_identity"] == "lee_m"
    assert {p["paper_id"] for p in g["papers"]} == {"S1", "S2"}


def test_groups_endpoint_empty_when_no_authors(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="A", doi="10.1/a")
    client = TestClient(create_app(AppConfig(library_dir=library)))
    assert client.get("/groups").json() == {"groups": []}
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_groups.py -v
```

Expected: FAIL — `AppConfig` has no `authors_db` (AttributeError) / no `/groups` route (404).

- [ ] **Step 3: Add the `authors_db` property.** In `desktop_app/src/autoreview_app/config.py`, add this property to `AppConfig` (next to `index_db`):

```python
    @property
    def authors_db(self) -> Path:
        """DOI-keyed author store, kept beside the library dir."""
        return self.library_dir.parent / "authors.db"
```

- [ ] **Step 4: Add the route.** In `desktop_app/src/autoreview_app/api.py`, add imports near the other local imports:

```python
from .groups.cluster import cluster_papers
from .groups.store import load_authors
```

Inside `create_app`, before `return app`, add:

```python
    @app.get("/groups")
    def groups() -> dict:
        reindex(config.library_dir, config.index_db)
        papers = query_papers(config.index_db)
        authors_by_doi = load_authors(config.authors_db)
        return {"groups": cluster_papers(papers, authors_by_doi)}
```

(`reindex` and `query_papers` are already imported from M4a. Leave existing routes unchanged.)

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_groups.py -v
```

Expected: PASS (2 passed). Then confirm no regression: `.venv\Scripts\python -m pytest tests/test_api_browse.py tests/test_config.py -v` → 6 passed.

- [ ] **Step 6: Run the FULL suite** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -q
```

Expected: all green. Report the summary line.

- [ ] **Step 7: Commit.**

```powershell
git add desktop_app/src/autoreview_app/config.py desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api_groups.py
git commit -m "feat(desktop): GET /groups clusters library papers by senior author"
```

---

## Done criteria for M4b

- Author identity key (family + first initial; coarse-merges name variants) + senior-author anchor (last author).
- DOI-keyed author store (upsert, rebuildable, concurrency-safe).
- `cluster_papers` groups library papers by senior-author identity, with evidence + size; ungroupable papers (no authors) are skipped.
- `GET /groups` joins the library index + author store by DOI and returns groups.
- Full suite green. Branch `feat/desktop-app-m4b`; not pushed.

## Out of scope for M4b (later)

- **The "C" co-authorship community** auxiliary signal (merge groups with high member overlap; flag same-name-different-community for AI adjudication) — a follow-up; M4b ships the dominant "A" senior-author signal.
- **ORCID / OpenAlex-id identity** (stronger than name) — needs `CrossrefSource._to_record` to capture ORCID (currently dropped) and the store to keep it; a follow-up.
- **Populating the author store at runtime** from the discovery→download flow (deferred with M3's real wiring). M4b's store is populated by tests / a future wiring task; clustering itself is complete and correct.
- **AI adjudication** of ambiguous same-name merges.

---

## Self-review (planner)

- **Coverage vs roadmap M4 (clustering half) + design §5B:** anchor = senior (last) author [§5B.2], identity = name key (ORCID stronger key noted as follow-up) [§5B.2], grouping with evidence + confidence-ish (evidence string) [§5B.5], `GET /groups` [§5B.6]. The "C" co-authorship aux and AI adjudication are explicitly deferred (matches "A 为主 C 辅助"). ✓
- **Placeholders:** none — full code/commands per step. ✓
- **Type/name consistency:** `author_identity(name)`, `anchor_author(authors)` (Task 1) used by `cluster_papers` (Task 3). `save_authors(db, doi, authors)`/`load_authors(db)` (Task 2) used by the endpoint (Task 4). `cluster_papers(papers, authors_by_doi)` (Task 3) used by the endpoint. `AppConfig.authors_db` (Task 4) + existing `index_db`/`reindex`/`query_papers` (M4a). Endpoint joins library papers (which carry `doi` from M4a index) to `authors_by_doi`. ✓
