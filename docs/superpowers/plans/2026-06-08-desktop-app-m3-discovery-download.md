# Desktop App M3 — Discovery + Download (plugin framework) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user build a starter library without leaving the app: import a citation file (RIS) OR search an open-access source for papers, then batch-download the selected PDFs — each downloaded PDF then flows into the existing M2 import (`import_pdf`). Built on an extensible **source-plugin framework** so new sources (Sci-Hub, screenshot, BibTeX) can be added later.

**Architecture:** Every network call goes through an injected `Transport` (get_json / get_bytes), so the whole layer is tested offline with a fake transport (the same fake-client discipline used for AI in M2b). A `CitationRecord` is the normalized unit (doi, title, authors, year, journal, optional pdf_url). A `SourcePlugin` declares capabilities (`can_search`, `can_fetch`) and implements `search(query, transport)` and/or `fetch(record, transport)`. A `SourceRegistry` holds plugins and routes search/fetch. The built-in source for M3 is **Crossref** (search → DOIs/metadata; it is metadata-only, so fetch falls to OA pdf_url when present). A `download` orchestrator fetches bytes via fetchable sources in priority order, writes PDFs, and de-dupes by SHA-256. New API routes expose RIS import, search, and a download job.

**Tech Stack:** Python 3.12 (`desktop_app/.venv`), stdlib `urllib`/`hashlib` (no new deps for the real transport), FastAPI, pytest. No real network in tests.

**Git:** branch `feat/desktop-app-m3`; commit per task; no push; user merges after review.

**Depends on:** M1 (app + jobs), M2 (`import_pdf`, `JobRegistry`). Run from `desktop_app/` with `.venv\Scripts\python`.

---

## Verified facts (from paper_pool source — do not re-derive)

- `paper_pool/scripts/paper_downloader.py` has `parse_ris(path) -> list[Article]` + a frozen `Article` dataclass (fields: index, title, authors[list], journal, year, doi, url, pii). RIS is a hand-rolled tag state machine: lines match `^([A-Z0-9]{2})  - ?(.*)$`; `TY` starts a record, `ER` ends it; multi-line continuation appends to the last tag; DOI = first `DO` tag. **BUT that module imports heavy Windows GUI libs (pyautogui/cv2/pywinauto), so it is NOT importable here** — re-implement a small clean RIS parser in the desktop app.
- No pure-HTTP download and no OA search exist anywhere — build new.
- SHA-256: use stdlib `hashlib` (paper_pool's `sha256_file` is the same; no need to import it).

---

## File Structure (all under `desktop_app/`)

- `src/autoreview_app/discovery/__init__.py`
- `src/autoreview_app/discovery/records.py` — `CitationRecord` dataclass + helpers
- `src/autoreview_app/discovery/ris.py` — `parse_ris_text(text) -> list[CitationRecord]`
- `src/autoreview_app/discovery/transport.py` — `Transport` Protocol + `UrllibTransport` (real, stdlib)
- `src/autoreview_app/discovery/sources/__init__.py`
- `src/autoreview_app/discovery/sources/base.py` — `SourcePlugin` Protocol + capability flags
- `src/autoreview_app/discovery/sources/crossref.py` — Crossref search source
- `src/autoreview_app/discovery/registry.py` — `SourceRegistry`
- `src/autoreview_app/discovery/download.py` — `download_records(...)` (fetch + sha256 dedupe)
- `src/autoreview_app/api.py` — MODIFY: `/discovery/import-ris`, `/discovery/search`, `/download`
- Tests: `tests/test_ris.py`, `tests/test_crossref_source.py`, `tests/test_registry.py`, `tests/test_download.py`, `tests/test_api_discovery.py`, `tests/_fake_transport.py`

Boundaries: `records` is pure data; `ris` is pure parsing; `transport` is the only thing that does HTTP; `sources/*` turn transport calls into records/bytes; `registry` routes; `download` orchestrates + dedupes; `api` wires HTTP. Everything except `UrllibTransport` is testable with a fake transport.

---

### Task 1: `CitationRecord` + RIS parser

**Files:**
- Create: `desktop_app/src/autoreview_app/discovery/__init__.py`
- Create: `desktop_app/src/autoreview_app/discovery/records.py`
- Create: `desktop_app/src/autoreview_app/discovery/ris.py`
- Test: `desktop_app/tests/test_ris.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_ris.py`:

```python
from autoreview_app.discovery.ris import parse_ris_text

SAMPLE = """TY  - JOUR
TI  - A Study of Methane Adsorption
AU  - Smith, John
AU  - Doe, Jane
T2  - Fuel
PY  - 2020
DO  - 10.1016/j.fuel.2020.12345
ER  -

TY  - JOUR
TI  - Second Paper
PY  - 2019
ER  -
"""


def test_parses_two_records():
    records = parse_ris_text(SAMPLE)
    assert len(records) == 2


def test_first_record_fields():
    rec = parse_ris_text(SAMPLE)[0]
    assert rec.title == "A Study of Methane Adsorption"
    assert rec.authors == ["Smith, John", "Doe, Jane"]
    assert rec.journal == "Fuel"
    assert rec.year == "2020"
    assert rec.doi == "10.1016/j.fuel.2020.12345"


def test_record_without_doi_has_empty_doi():
    rec = parse_ris_text(SAMPLE)[1]
    assert rec.doi == ""
    assert rec.title == "Second Paper"


def test_empty_text_gives_no_records():
    assert parse_ris_text("") == []
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_ris.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.discovery'`.

- [ ] **Step 3: Create the package + records** — `desktop_app/src/autoreview_app/discovery/__init__.py`:

```python
"""Discovery + download: find papers (RIS import / OA search) and fetch PDFs."""
```

`desktop_app/src/autoreview_app/discovery/records.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CitationRecord:
    """A normalized citation: enough to dedupe, display, and fetch a PDF."""

    title: str = ""
    doi: str = ""
    year: str = ""
    journal: str = ""
    authors: tuple[str, ...] = ()
    pdf_url: str = ""  # a direct open-access PDF url when a source provides one

    @property
    def key(self) -> str:
        """Dedup key: normalized DOI if present, else lowercased title."""
        return self.doi.lower() if self.doi else self.title.strip().lower()
```

- [ ] **Step 4: Implement the RIS parser** — `desktop_app/src/autoreview_app/discovery/ris.py`:

```python
from __future__ import annotations

import re

from .records import CitationRecord

_TAG = re.compile(r"^([A-Z0-9]{2})  - ?(.*)$")


def parse_ris_text(text: str) -> list[CitationRecord]:
    """Parse RIS text into CitationRecords. Hand-rolled tag state machine.

    TY starts a record, ER ends it; lines not matching a tag continue the last
    tag's value; AU may repeat (collected as authors).
    """
    records: list[CitationRecord] = []
    current: dict[str, list[str]] | None = None
    last_tag: str | None = None

    for line in text.splitlines():
        match = _TAG.match(line)
        if match:
            tag, value = match.group(1), match.group(2).strip()
            if tag == "TY":
                current = {}
                last_tag = None
                continue
            if tag == "ER":
                if current is not None:
                    records.append(_to_record(current))
                current = None
                last_tag = None
                continue
            if current is not None:
                current.setdefault(tag, []).append(value)
                last_tag = tag
        elif current is not None and last_tag is not None and line.strip():
            current[last_tag][-1] = (current[last_tag][-1] + " " + line.strip()).strip()

    return records


def _to_record(tags: dict[str, list[str]]) -> CitationRecord:
    def first(tag: str, *fallbacks: str) -> str:
        for key in (tag, *fallbacks):
            if tags.get(key):
                return tags[key][0].strip()
        return ""

    return CitationRecord(
        title=first("TI", "T1"),
        doi=first("DO"),
        year=first("PY", "Y1"),
        journal=first("T2", "JO", "JF"),
        authors=tuple(a.strip() for a in tags.get("AU", []) if a.strip()),
    )
```

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_ris.py -v
```

Expected: PASS (4 passed).

- [ ] **Step 6: Commit.**

```powershell
git checkout -b feat/desktop-app-m3
git add desktop_app/src/autoreview_app/discovery/__init__.py desktop_app/src/autoreview_app/discovery/records.py desktop_app/src/autoreview_app/discovery/ris.py desktop_app/tests/test_ris.py
git commit -m "feat(desktop): CitationRecord + RIS parser"
```

---

### Task 2: `Transport` seam (Protocol + urllib impl)

**Files:**
- Create: `desktop_app/src/autoreview_app/discovery/transport.py`
- Create: `desktop_app/tests/_fake_transport.py`
- Test: `desktop_app/tests/test_transport.py`

- [ ] **Step 1: Write the failing test** — `desktop_app/tests/test_transport.py`:

```python
from _fake_transport import FakeTransport


def test_fake_transport_returns_canned_json():
    t = FakeTransport(json_responses={"http://x/api": {"ok": True}})
    assert t.get_json("http://x/api", params={}) == {"ok": True}


def test_fake_transport_returns_canned_bytes():
    t = FakeTransport(byte_responses={"http://x/f.pdf": b"%PDF-1.4 data"})
    assert t.get_bytes("http://x/f.pdf") == b"%PDF-1.4 data"


def test_fake_transport_missing_url_raises():
    t = FakeTransport()
    try:
        t.get_bytes("http://missing")
    except KeyError:
        return
    raise AssertionError("expected KeyError for unmapped url")
```

- [ ] **Step 2: Run to verify it fails** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_transport.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named '_fake_transport'`.

- [ ] **Step 3: Define the Transport Protocol + urllib impl** — `desktop_app/src/autoreview_app/discovery/transport.py`:

```python
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any, Protocol

USER_AGENT = "AutoReviewDesktop/0.1 (mailto:unknown@example.com)"


class Transport(Protocol):
    def get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        ...

    def get_bytes(self, url: str) -> bytes:
        ...


class UrllibTransport:
    """Real HTTP via stdlib urllib. Polite User-Agent; modest timeout."""

    def __init__(self, timeout: float = 30.0):
        self._timeout = timeout

    def get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        full = url
        if params:
            full = f"{url}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(full, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_bytes(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            return resp.read()
```

- [ ] **Step 4: Create the fake transport test util** — `desktop_app/tests/_fake_transport.py`:

```python
from __future__ import annotations

from typing import Any


class FakeTransport:
    """Offline Transport: returns canned JSON/bytes keyed by url. Records calls."""

    def __init__(
        self,
        json_responses: dict[str, dict[str, Any]] | None = None,
        byte_responses: dict[str, bytes] | None = None,
    ):
        self._json = json_responses or {}
        self._bytes = byte_responses or {}
        self.json_calls: list[tuple[str, dict[str, str]]] = []
        self.byte_calls: list[str] = []

    def get_json(self, url: str, params: dict[str, str]) -> dict[str, Any]:
        self.json_calls.append((url, params))
        return self._json[url]

    def get_bytes(self, url: str) -> bytes:
        self.byte_calls.append(url)
        return self._bytes[url]
```

- [ ] **Step 5: Run to verify it passes** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_transport.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/src/autoreview_app/discovery/transport.py desktop_app/tests/_fake_transport.py desktop_app/tests/test_transport.py
git commit -m "feat(desktop): injectable Transport seam + fake transport"
```

---

### Task 3: `SourcePlugin` framework + Crossref search source

**Files:**
- Create: `desktop_app/src/autoreview_app/discovery/sources/__init__.py`
- Create: `desktop_app/src/autoreview_app/discovery/sources/base.py`
- Create: `desktop_app/src/autoreview_app/discovery/sources/crossref.py`
- Test: `desktop_app/tests/test_crossref_source.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_crossref_source.py`:

```python
from _fake_transport import FakeTransport

from autoreview_app.discovery.sources.crossref import CrossrefSource

CROSSREF_URL = "https://api.crossref.org/works"

CANNED = {
    "message": {
        "items": [
            {
                "DOI": "10.1016/j.fuel.2020.12345",
                "title": ["A Study of Methane Adsorption"],
                "container-title": ["Fuel"],
                "published": {"date-parts": [[2020, 5]]},
                "author": [{"family": "Smith", "given": "John"}],
            },
            {
                "DOI": "10.1000/xyz",
                "title": ["Untitled Dataset"],
                "container-title": [],
                "issued": {"date-parts": [[2018]]},
                "author": [],
            },
        ]
    }
}


def test_capabilities():
    src = CrossrefSource()
    assert src.name == "crossref"
    assert src.can_search is True
    assert src.can_fetch is False


def test_search_maps_items_to_records():
    transport = FakeTransport(json_responses={CROSSREF_URL: CANNED})
    records = CrossrefSource().search("methane", transport, rows=2)

    assert transport.json_calls[0][0] == CROSSREF_URL
    assert transport.json_calls[0][1]["query"] == "methane"
    assert transport.json_calls[0][1]["rows"] == "2"

    assert records[0].doi == "10.1016/j.fuel.2020.12345"
    assert records[0].title == "A Study of Methane Adsorption"
    assert records[0].journal == "Fuel"
    assert records[0].year == "2020"
    assert records[0].authors == ("Smith, John",)
    assert records[1].year == "2018"
    assert records[1].journal == ""
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_crossref_source.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.discovery.sources'`.

- [ ] **Step 3: Define the source interface** — `desktop_app/src/autoreview_app/discovery/sources/__init__.py`:

```python
"""Pluggable discovery/download sources (OA built-in; Sci-Hub/screenshot later)."""
```

`desktop_app/src/autoreview_app/discovery/sources/base.py`:

```python
from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..records import CitationRecord
from ..transport import Transport


@runtime_checkable
class SourcePlugin(Protocol):
    """A discovery/download source. Declares which capabilities it supports."""

    name: str
    can_search: bool
    can_fetch: bool

    def search(self, query: str, transport: Transport, rows: int = 20) -> list[CitationRecord]:
        ...

    def fetch(self, record: CitationRecord, transport: Transport) -> bytes | None:
        ...
```

- [ ] **Step 4: Implement the Crossref source** — `desktop_app/src/autoreview_app/discovery/sources/crossref.py`:

```python
from __future__ import annotations

from typing import Any

from ..records import CitationRecord
from ..transport import Transport

CROSSREF_WORKS_URL = "https://api.crossref.org/works"


class CrossrefSource:
    """Search Crossref for works -> CitationRecords (metadata + DOI). No PDF fetch."""

    name = "crossref"
    can_search = True
    can_fetch = False

    def search(self, query: str, transport: Transport, rows: int = 20) -> list[CitationRecord]:
        data = transport.get_json(CROSSREF_WORKS_URL, {"query": query, "rows": str(rows)})
        items = (data.get("message") or {}).get("items") or []
        return [self._to_record(item) for item in items]

    def fetch(self, record: CitationRecord, transport: Transport) -> bytes | None:
        return None  # Crossref is metadata-only

    def _to_record(self, item: dict[str, Any]) -> CitationRecord:
        title_list = item.get("title") or []
        journal_list = item.get("container-title") or []
        authors = tuple(
            f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
            for a in (item.get("author") or [])
            if a.get("family") or a.get("given")
        )
        return CitationRecord(
            title=(title_list[0] if title_list else "").strip(),
            doi=(item.get("DOI") or "").strip(),
            year=_year(item),
            journal=(journal_list[0] if journal_list else "").strip(),
            authors=authors,
        )


def _year(item: dict[str, Any]) -> str:
    for key in ("published", "issued", "published-online", "published-print"):
        parts = ((item.get(key) or {}).get("date-parts") or [[]])
        if parts and parts[0]:
            return str(parts[0][0])
    return ""
```

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_crossref_source.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/src/autoreview_app/discovery/sources/__init__.py desktop_app/src/autoreview_app/discovery/sources/base.py desktop_app/src/autoreview_app/discovery/sources/crossref.py desktop_app/tests/test_crossref_source.py
git commit -m "feat(desktop): SourcePlugin framework + Crossref search source"
```

---

### Task 4: `SourceRegistry`

**Files:**
- Create: `desktop_app/src/autoreview_app/discovery/registry.py`
- Test: `desktop_app/tests/test_registry.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_registry.py`:

```python
from autoreview_app.discovery.records import CitationRecord
from autoreview_app.discovery.registry import SourceRegistry


class _Searchable:
    name = "searchy"
    can_search = True
    can_fetch = False

    def search(self, query, transport, rows=20):
        return [CitationRecord(title=f"hit:{query}")]

    def fetch(self, record, transport):
        return None


class _Fetchable:
    name = "fetchy"
    can_search = False
    can_fetch = True

    def search(self, query, transport, rows=20):
        return []

    def fetch(self, record, transport):
        return b"%PDF-1.4"


def test_register_and_list():
    reg = SourceRegistry()
    reg.register(_Searchable())
    reg.register(_Fetchable())
    assert {s.name for s in reg.all()} == {"searchy", "fetchy"}


def test_searchable_and_fetchable_filters():
    reg = SourceRegistry()
    reg.register(_Searchable())
    reg.register(_Fetchable())
    assert [s.name for s in reg.searchable()] == ["searchy"]
    assert [s.name for s in reg.fetchable()] == ["fetchy"]


def test_get_by_name():
    reg = SourceRegistry()
    s = _Searchable()
    reg.register(s)
    assert reg.get("searchy") is s
    assert reg.get("missing") is None
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_registry.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.discovery.registry'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/discovery/registry.py`:

```python
from __future__ import annotations

from .sources.base import SourcePlugin


class SourceRegistry:
    """Holds discovery/download source plugins; routes by capability."""

    def __init__(self) -> None:
        self._sources: list[SourcePlugin] = []

    def register(self, source: SourcePlugin) -> None:
        self._sources.append(source)

    def all(self) -> list[SourcePlugin]:
        return list(self._sources)

    def searchable(self) -> list[SourcePlugin]:
        return [s for s in self._sources if s.can_search]

    def fetchable(self) -> list[SourcePlugin]:
        return [s for s in self._sources if s.can_fetch]

    def get(self, name: str) -> SourcePlugin | None:
        for s in self._sources:
            if s.name == name:
                return s
        return None
```

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_registry.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/discovery/registry.py desktop_app/tests/test_registry.py
git commit -m "feat(desktop): source registry routes by capability"
```

---

### Task 5: `download_records` — fetch + SHA-256 dedupe

**Files:**
- Create: `desktop_app/src/autoreview_app/discovery/download.py`
- Test: `desktop_app/tests/test_download.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_download.py`:

```python
import hashlib
from pathlib import Path

from _fake_transport import FakeTransport

from autoreview_app.discovery.records import CitationRecord
from autoreview_app.discovery.download import download_records


class _OASource:
    name = "oa"
    can_search = False
    can_fetch = True

    def search(self, query, transport, rows=20):
        return []

    def fetch(self, record, transport):
        if record.pdf_url:
            return transport.get_bytes(record.pdf_url)
        return None


def test_downloads_pdf_and_reports(tmp_path: Path):
    rec = CitationRecord(title="P1", doi="10.1/a", pdf_url="http://x/a.pdf")
    transport = FakeTransport(byte_responses={"http://x/a.pdf": b"%PDF-1.4 AAA"})

    results = download_records(
        [rec], fetchers=[_OASource()], transport=transport, dest_dir=tmp_path,
    )

    assert len(results) == 1
    r = results[0]
    assert r["status"] == "downloaded"
    saved = Path(r["path"])
    assert saved.exists()
    assert saved.read_bytes() == b"%PDF-1.4 AAA"
    assert r["sha256"] == hashlib.sha256(b"%PDF-1.4 AAA").hexdigest()


def test_duplicate_bytes_are_skipped(tmp_path: Path):
    a = CitationRecord(title="A", doi="10.1/a", pdf_url="http://x/a.pdf")
    b = CitationRecord(title="B", doi="10.1/b", pdf_url="http://x/b.pdf")
    transport = FakeTransport(byte_responses={
        "http://x/a.pdf": b"%PDF same", "http://x/b.pdf": b"%PDF same",
    })

    results = download_records([a, b], fetchers=[_OASource()], transport=transport, dest_dir=tmp_path)

    statuses = [r["status"] for r in results]
    assert statuses == ["downloaded", "duplicate"]
    assert len(list(tmp_path.glob("*.pdf"))) == 1


def test_no_full_text_when_no_fetcher_succeeds(tmp_path: Path):
    rec = CitationRecord(title="NoPdf", doi="10.1/c")  # no pdf_url
    transport = FakeTransport()
    results = download_records([rec], fetchers=[_OASource()], transport=transport, dest_dir=tmp_path)
    assert results[0]["status"] == "no_full_text"
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_download.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.discovery.download'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/discovery/download.py`:

```python
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .records import CitationRecord
from .sources.base import SourcePlugin
from .transport import Transport


def _safe_stem(record: CitationRecord, index: int) -> str:
    basis = record.doi or record.title or f"paper{index}"
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", basis).strip("_")
    return (cleaned[:60].strip("_") or f"paper{index}")


def download_records(
    records: list[CitationRecord],
    fetchers: list[SourcePlugin],
    transport: Transport,
    dest_dir: Path,
) -> list[dict[str, Any]]:
    """Fetch each record's PDF via the first fetcher that returns bytes; dedupe by SHA-256.

    Per-record status: downloaded | duplicate | no_full_text.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    seen: dict[str, str] = {}  # sha256 -> path
    results: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        data: bytes | None = None
        for fetcher in fetchers:
            if not fetcher.can_fetch:
                continue
            data = fetcher.fetch(record, transport)
            if data:
                break

        if not data:
            results.append({"key": record.key, "status": "no_full_text", "path": None, "sha256": None})
            continue

        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            results.append({"key": record.key, "status": "duplicate", "path": seen[digest], "sha256": digest})
            continue

        path = dest_dir / f"{_safe_stem(record, index)}.pdf"
        path.write_bytes(data)
        seen[digest] = str(path)
        results.append({"key": record.key, "status": "downloaded", "path": str(path), "sha256": digest})

    return results
```

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_download.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/discovery/download.py desktop_app/tests/test_download.py
git commit -m "feat(desktop): download_records fetches OA PDFs + dedupes by sha256"
```

---

### Task 6: Discovery API routes

**Files:**
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api_discovery.py`

`create_app` gains an optional `search_runner` (so the search route is testable without network). RIS import is pure (no network), so it runs inline.

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_api_discovery.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig

SAMPLE_RIS = "TY  - JOUR\nTI  - Hello Paper\nDO  - 10.1/x\nER  -\n"


def _client(tmp_path: Path, search_runner=None):
    app = create_app(AppConfig(library_dir=tmp_path / "library"), search_runner=search_runner)
    return TestClient(app)


def test_import_ris_returns_records(tmp_path: Path):
    client = _client(tmp_path)
    resp = client.post("/discovery/import-ris", json={"text": SAMPLE_RIS})
    assert resp.status_code == 200
    records = resp.json()["records"]
    assert records[0]["title"] == "Hello Paper"
    assert records[0]["doi"] == "10.1/x"


def test_search_uses_injected_runner(tmp_path: Path):
    def fake_search(query: str):
        return [{"title": f"result for {query}", "doi": "10.1/q", "year": "", "journal": "", "authors": [], "pdf_url": ""}]

    client = _client(tmp_path, search_runner=fake_search)
    resp = client.post("/discovery/search", json={"query": "methane"})
    assert resp.status_code == 200
    assert resp.json()["records"][0]["title"] == "result for methane"
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_discovery.py -v
```

Expected: FAIL — `create_app()` has no `search_runner` kwarg (TypeError).

- [ ] **Step 3: Implement.** Edit `desktop_app/src/autoreview_app/api.py`. Add these imports near the top (after the existing imports):

```python
from .discovery.records import CitationRecord
from .discovery.ris import parse_ris_text
```

Add a type alias next to `ImportRunner`:

```python
# A search runner takes a query string and returns a list of record dicts.
SearchRunner = Callable[[str], list[dict[str, Any]]]
```

Add two request models next to `ImportRequest`:

```python
class RisRequest(BaseModel):
    text: str


class SearchRequest(BaseModel):
    query: str
```

Add a `_record_to_dict` helper at module level:

```python
def _record_to_dict(rec: CitationRecord) -> dict[str, Any]:
    return {
        "title": rec.title, "doi": rec.doi, "year": rec.year,
        "journal": rec.journal, "authors": list(rec.authors), "pdf_url": rec.pdf_url,
    }
```

Change the `create_app` signature to add `search_runner`:

```python
def create_app(
    config: AppConfig,
    import_runner: ImportRunner | None = None,
    search_runner: SearchRunner | None = None,
) -> FastAPI:
```

Inside `create_app`, before `return app`, add the two routes:

```python
    @app.post("/discovery/import-ris")
    def import_ris(req: RisRequest) -> dict:
        records = parse_ris_text(req.text)
        return {"records": [_record_to_dict(r) for r in records]}

    @app.post("/discovery/search")
    def search(req: SearchRequest) -> dict:
        if search_runner is None:
            raise HTTPException(status_code=503, detail="search not configured")
        return {"records": search_runner(req.query)}
```

(Leave the existing routes and `_default_import_runner` unchanged.)

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_discovery.py -v
```

Expected: PASS (2 passed). Then confirm no regression: `.venv\Scripts\python -m pytest tests/test_api.py tests/test_api_import.py -v` → 6 passed.

- [ ] **Step 5: Run the FULL suite** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -q
```

Expected: all green. Report the summary line.

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api_discovery.py
git commit -m "feat(desktop): /discovery/import-ris + /discovery/search routes"
```

---

## Done criteria for M3

- RIS text → `CitationRecord`s (offline, pure).
- A `SourcePlugin` framework with capability routing + a Crossref search source (HTTP via injected transport).
- `download_records` fetches OA PDFs via fetchable sources and de-dupes by SHA-256.
- API: `/discovery/import-ris`, `/discovery/search` (the search runner injectable for tests).
- Full suite green. Branch `feat/desktop-app-m3`; not pushed.

## Out of scope for M3 (later)

- Wiring a real `UrllibTransport` + Crossref into the app's default search runner and a real `/download` job that feeds `import_pdf` — a thin follow-up once the offline pieces are proven; the orchestration pattern mirrors `_default_import_runner`.
- Real OA fetch sources (OpenAlex/arXiv/Unpaywall pdf_url resolution) — add as more `SourcePlugin`s.
- Sci-Hub plugin (default-off, user mirror) + screenshot-download plugin (Windows-only) — reference plugins, deferred.
- BibTeX import.
- A real-network smoke (Crossref) — run manually, not in the auto suite.

---

## Self-review (planner)

- **Coverage vs roadmap M3:** SourcePlugin framework + capability routing (Task 3/4), RIS import (Task 1), a built-in OA search source (Task 3), download + sha256 dedupe (Task 5), API (Task 6). Real-network wiring + Sci-Hub/screenshot reference plugins + multi-source explicitly deferred. ✓
- **Placeholders:** none — full code/commands per step. Network is isolated behind `Transport`; tests inject `FakeTransport`. ✓
- **Type/name consistency:** `CitationRecord` (records.py) used everywhere; `Transport.get_json/get_bytes` matched by `UrllibTransport` and `FakeTransport`; `SourcePlugin` (name/can_search/can_fetch/search/fetch) matched by `CrossrefSource` and the test sources; `SourceRegistry.searchable/fetchable/get` (Task 4) used conceptually by download (Task 5 takes `fetchers` list directly). `create_app(config, import_runner=None, search_runner=None)` extends the M2b signature additively (existing callers unaffected). ✓
