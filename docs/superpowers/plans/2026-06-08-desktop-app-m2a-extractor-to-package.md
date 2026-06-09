# Desktop App M2a — Extractor → Clean Package (offline) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a PDF into the engine's "clean package" (`library/Sxx/content_blocks.json` etc.) entirely offline, via a pluggable extractor whose default implementation is PyMuPDF — by emitting a Docling-compatible JSON and feeding it to the engine's existing `build_clean_package`, with no AI and no Docling install required.

**Architecture:** The real seam in the engine is `PDF → Docling-shaped JSON → build_clean_package → clean package`. So the extractor's job is "PDF → a minimal Docling-compatible JSON dict", not "produce the clean package directly". A `PyMuPDFExtractor` reads text blocks with PyMuPDF (`fitz`) and assembles that JSON via a small pure shaping module. An `engine_bridge` puts `Document_Decomposer/src` on `sys.path`, allocates the next `Sxx` id, writes the JSON to a `Sxx_*.json` file (the engine derives the paper id from the filename), and calls the engine's `build_clean_package` unchanged. Everything is deterministic and unit-testable; tests synthesize tiny PDFs with `fitz` itself.

**Tech Stack:** Python 3.12 (existing `desktop_app/.venv`), PyMuPDF (`pymupdf`, import name `fitz`), the existing `docdecomp` engine package (stdlib-only), pytest.

**Git:** Substantial change → branch `feat/desktop-app-m2a` (per repo `CLAUDE.md`). Commit after each task. No push; user merges after review.

**Depends on:** M1 (the `desktop_app/` package, its `conftest.py`, and `.venv`). Run all commands from `desktop_app/` using `.venv\Scripts\python`.

---

## Verified engine contract (read from source — do not re-derive)

`Document_Decomposer/src/docdecomp/package_builder.py`:

- `build_clean_package(json_path: Path, md_path: Path | None, output_root: Path, pdf_dirs: list[Path] | None = None) -> BuildResult`.
- It reads the Docling JSON at `json_path`, derives `paper_id` from the **filename stem** via `sample_id_from_stem` (regex `^(S\d+)_`), and writes `output_root/<paper_id>/{content_blocks.json, evidence.json, metadata_candidates.json, content.md}` (+ empty `figures/`, `tables/`).
- Body order comes from `data["body"]["children"]` — a list of `{"$ref": "#/texts/<i>"}` (also supports `#/pictures`, `#/tables`, `#/groups`). Refs resolve by integer index into `data["texts"]` etc.
- A text item is **kept** only if `label` ∈ `{text, section_header, list_item, caption, formula, footnote}` AND `content_layer != "furniture"` AND it is not "noise" (empty / pure number / known furniture phrases). Text comes from `item["text"]` (or `item["orig"]`). Page from `item["prov"][0]["page_no"]` (int); `item["prov"][0]["bbox"]` is stored as-is (any dict).
- `metadata_candidates` reads first-page (`page_no == 1`) texts plus `data["name"]` and `data["origin"]["filename"]` for title/doi/year/journal heuristics.
- `docdecomp/__init__.py` is empty; importing `docdecomp.package_builder` pulls only stdlib + `docdecomp.io_utils` (stdlib). No heavy deps.

So the **minimal Docling JSON** the extractor must emit is:

```json
{
  "schema_name": "DoclingDocument",
  "name": "<pdf stem>",
  "origin": {"filename": "<pdf filename>"},
  "body": {"children": [{"$ref": "#/texts/0"}, {"$ref": "#/texts/1"}]},
  "groups": [],
  "texts": [
    {"self_ref": "#/texts/0", "label": "text", "text": "...", "orig": "...",
     "content_layer": "body", "prov": [{"page_no": 1, "bbox": {"l": 0, "t": 0, "r": 0, "b": 0, "coord_origin": "TOPLEFT"}}]}
  ],
  "pictures": [],
  "tables": []
}
```

---

## File Structure

Created/modified in this milestone (all under `desktop_app/`):

- `requirements.txt` — add `pymupdf`
- `src/autoreview_app/extract/__init__.py` — new subpackage marker
- `src/autoreview_app/extract/docling_json.py` — pure shaping: text items → minimal Docling JSON dict
- `src/autoreview_app/extract/base.py` — `PdfExtractor` Protocol (the pluggable seam)
- `src/autoreview_app/extract/pymupdf_extractor.py` — `PyMuPDFExtractor` (PDF → Docling JSON via `fitz`)
- `src/autoreview_app/paper_ids.py` — `allocate_paper_id(library_dir)`
- `src/autoreview_app/engine_bridge.py` — puts engine `src` on path; `build_package_from_pdf(...)`
- `tests/test_docling_json.py`, `tests/test_pymupdf_extractor.py`, `tests/test_paper_ids.py`, `tests/test_engine_bridge.py`
- `tests/_pdf_helpers.py` — shared helper to synthesize a tiny PDF with `fitz`

Responsibilities stay isolated: `docling_json` shapes data (no I/O, no fitz), `pymupdf_extractor` reads PDFs (fitz only), `paper_ids` allocates ids (filesystem only), `engine_bridge` orchestrates + touches the engine. Each is independently testable.

---

### Task 1: Add PyMuPDF + engine-bridge import smoke

**Files:**
- Modify: `desktop_app/requirements.txt`
- Create: `desktop_app/src/autoreview_app/extract/__init__.py`
- Create: `desktop_app/src/autoreview_app/engine_bridge.py`
- Test: `desktop_app/tests/test_engine_bridge_import.py`

- [ ] **Step 1: Add the dependency.** Append `pymupdf>=1.24` to `desktop_app/requirements.txt` (keep existing lines). The file becomes:

```text
fastapi>=0.110
uvicorn>=0.29
pywebview>=5.0
httpx>=0.27
pytest>=8.0
pymupdf>=1.24
```

- [ ] **Step 2: Install it.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
```

Expected: installs `pymupdf` (provides the `fitz` module) without error.

- [ ] **Step 3: Create the subpackage marker.** Create `desktop_app/src/autoreview_app/extract/__init__.py`:

```python
"""Pluggable PDF extraction backends (PyMuPDF default; Docling optional later)."""
```

- [ ] **Step 4: Write the failing import test.** Create `desktop_app/tests/test_engine_bridge_import.py`:

```python
def test_engine_bridge_exposes_build_clean_package():
    from autoreview_app import engine_bridge

    # engine_bridge must have put Document_Decomposer/src on sys.path and
    # imported the engine's deterministic package builder.
    assert callable(engine_bridge.build_clean_package)
    assert callable(engine_bridge.build_package_from_pdf)
```

- [ ] **Step 5: Run it to verify it fails.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_engine_bridge_import.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.engine_bridge'`.

- [ ] **Step 6: Create the engine bridge (import wiring only for now).** Create `desktop_app/src/autoreview_app/engine_bridge.py`:

```python
from __future__ import annotations

import sys
from pathlib import Path

# engine_bridge.py lives at desktop_app/src/autoreview_app/engine_bridge.py.
# parents[3] is the repo root; the engine source is Document_Decomposer/src.
ENGINE_SRC = Path(__file__).resolve().parents[3] / "Document_Decomposer" / "src"
if ENGINE_SRC.is_dir() and str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from docdecomp.package_builder import build_clean_package  # noqa: E402


def build_package_from_pdf():  # placeholder, implemented in Task 5
    raise NotImplementedError
```

- [ ] **Step 7: Run the test to verify it passes.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_engine_bridge_import.py -v
```

Expected: PASS (1 passed). If it fails with `ModuleNotFoundError: No module named 'docdecomp'`, STOP and report — the `ENGINE_SRC` path is wrong (verify `Document_Decomposer/src/docdecomp/package_builder.py` exists relative to the repo root).

- [ ] **Step 8: Commit.**

```powershell
git checkout -b feat/desktop-app-m2a
git add desktop_app/requirements.txt desktop_app/src/autoreview_app/extract/__init__.py desktop_app/src/autoreview_app/engine_bridge.py desktop_app/tests/test_engine_bridge_import.py
git commit -m "feat(desktop): engine bridge imports build_clean_package + add pymupdf"
```

---

### Task 2: `build_docling_json` — shape text items into minimal Docling JSON

**Files:**
- Create: `desktop_app/src/autoreview_app/extract/docling_json.py`
- Test: `desktop_app/tests/test_docling_json.py`

- [ ] **Step 1: Write the failing tests.** Create `desktop_app/tests/test_docling_json.py`:

```python
from autoreview_app.extract.docling_json import build_docling_json


def _items():
    return [
        {"page_no": 1, "text": "First block.", "bbox": {"l": 0, "t": 0, "r": 1, "b": 1}},
        {"page_no": 2, "text": "Second block.", "bbox": {"l": 0, "t": 0, "r": 1, "b": 1}},
    ]


def test_top_level_shape():
    doc = build_docling_json("mypaper", "mypaper.pdf", _items())
    assert doc["name"] == "mypaper"
    assert doc["origin"]["filename"] == "mypaper.pdf"
    assert doc["pictures"] == []
    assert doc["tables"] == []
    assert doc["groups"] == []


def test_body_children_reference_texts_in_order():
    doc = build_docling_json("mypaper", "mypaper.pdf", _items())
    assert [c["$ref"] for c in doc["body"]["children"]] == ["#/texts/0", "#/texts/1"]


def test_each_text_item_has_required_fields():
    doc = build_docling_json("mypaper", "mypaper.pdf", _items())
    t0 = doc["texts"][0]
    assert t0["label"] == "text"
    assert t0["content_layer"] == "body"
    assert t0["text"] == "First block."
    assert t0["orig"] == "First block."
    assert t0["prov"][0]["page_no"] == 1
    assert t0["prov"][0]["bbox"] == {"l": 0, "t": 0, "r": 1, "b": 1}


def test_empty_items_give_empty_body_and_texts():
    doc = build_docling_json("p", "p.pdf", [])
    assert doc["texts"] == []
    assert doc["body"]["children"] == []
```

- [ ] **Step 2: Run to verify they fail.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_docling_json.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.extract.docling_json'`.

- [ ] **Step 3: Implement.** Create `desktop_app/src/autoreview_app/extract/docling_json.py`:

```python
from __future__ import annotations

from typing import Any

# A "text item" is a plain dict: {"page_no": int, "text": str, "bbox": dict}.
# This module shapes a list of them into the minimal Docling-compatible JSON
# that the engine's build_clean_package consumes. Pure data; no I/O, no fitz.


def build_docling_json(
    name: str,
    origin_filename: str,
    text_items: list[dict[str, Any]],
) -> dict[str, Any]:
    texts: list[dict[str, Any]] = []
    children: list[dict[str, str]] = []
    for index, item in enumerate(text_items):
        ref = f"#/texts/{index}"
        texts.append(
            {
                "self_ref": ref,
                "label": "text",
                "text": item["text"],
                "orig": item["text"],
                "content_layer": "body",
                "prov": [{"page_no": item["page_no"], "bbox": item["bbox"]}],
            }
        )
        children.append({"$ref": ref})
    return {
        "schema_name": "DoclingDocument",
        "name": name,
        "origin": {"filename": origin_filename},
        "body": {"children": children},
        "groups": [],
        "texts": texts,
        "pictures": [],
        "tables": [],
    }
```

- [ ] **Step 4: Run to verify they pass.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_docling_json.py -v
```

Expected: PASS (4 passed).

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/extract/docling_json.py desktop_app/tests/test_docling_json.py
git commit -m "feat(desktop): shape text items into minimal Docling JSON"
```

---

### Task 3: `PyMuPDFExtractor` — PDF → Docling JSON

**Files:**
- Create: `desktop_app/tests/_pdf_helpers.py`
- Create: `desktop_app/src/autoreview_app/extract/base.py`
- Create: `desktop_app/src/autoreview_app/extract/pymupdf_extractor.py`
- Test: `desktop_app/tests/test_pymupdf_extractor.py`

- [ ] **Step 1: Create the shared PDF helper.** Create `desktop_app/tests/_pdf_helpers.py`:

```python
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def make_pdf(path: Path, pages_text: list[str]) -> Path:
    """Write a tiny PDF; one page per string, the string drawn as text."""
    doc = fitz.open()
    try:
        for text in pages_text:
            page = doc.new_page()
            page.insert_text((72, 72), text)
        doc.save(str(path))
    finally:
        doc.close()
    return path
```

- [ ] **Step 2: Write the failing tests.** Create `desktop_app/tests/test_pymupdf_extractor.py`:

```python
from pathlib import Path

from _pdf_helpers import make_pdf

from autoreview_app.extract.pymupdf_extractor import PyMuPDFExtractor


def test_extracts_text_with_page_numbers(tmp_path: Path):
    pdf = make_pdf(tmp_path / "paper.pdf", ["Hello abstract world.", "Methods section here."])
    doc = PyMuPDFExtractor().extract(pdf)

    assert doc["name"] == "paper"
    assert doc["origin"]["filename"] == "paper.pdf"

    all_text = " ".join(t["text"] for t in doc["texts"])
    assert "Hello abstract world." in all_text
    assert "Methods section here." in all_text

    pages = {t["prov"][0]["page_no"] for t in doc["texts"]}
    assert pages == {1, 2}


def test_body_children_match_texts_count(tmp_path: Path):
    pdf = make_pdf(tmp_path / "p.pdf", ["One.", "Two."])
    doc = PyMuPDFExtractor().extract(pdf)
    assert len(doc["body"]["children"]) == len(doc["texts"])


def test_extractor_declares_name():
    assert PyMuPDFExtractor().name == "pymupdf"
```

- [ ] **Step 3: Run to verify they fail.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_pymupdf_extractor.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.extract.pymupdf_extractor'`.

- [ ] **Step 4: Define the extractor interface.** Create `desktop_app/src/autoreview_app/extract/base.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class PdfExtractor(Protocol):
    """A pluggable PDF backend: PDF in, a Docling-compatible JSON dict out.

    Implementations (PyMuPDF now; Docling later) emit the same JSON shape so the
    engine's build_clean_package can consume either one unchanged.
    """

    name: str

    def extract(self, pdf_path: Path) -> dict[str, Any]:
        ...
```

- [ ] **Step 5: Implement the PyMuPDF extractor.** Create `desktop_app/src/autoreview_app/extract/pymupdf_extractor.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from .docling_json import build_docling_json


class PyMuPDFExtractor:
    """Extract text blocks from a PDF using PyMuPDF and shape them as Docling JSON."""

    name = "pymupdf"

    def extract(self, pdf_path: Path) -> dict[str, Any]:
        text_items: list[dict[str, Any]] = []
        doc = fitz.open(str(pdf_path))
        try:
            for page_index in range(doc.page_count):
                page = doc[page_index]
                page_no = page_index + 1
                for block in page.get_text("blocks"):
                    # block = (x0, y0, x1, y1, text, block_no, block_type)
                    x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
                    text = (text or "").strip()
                    if not text:
                        continue
                    text_items.append(
                        {
                            "page_no": page_no,
                            "text": text,
                            "bbox": {
                                "l": x0,
                                "t": y0,
                                "r": x1,
                                "b": y1,
                                "coord_origin": "TOPLEFT",
                            },
                        }
                    )
        finally:
            doc.close()
        return build_docling_json(
            name=pdf_path.stem,
            origin_filename=pdf_path.name,
            text_items=text_items,
        )
```

- [ ] **Step 6: Run to verify they pass.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_pymupdf_extractor.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 7: Commit.**

```powershell
git add desktop_app/tests/_pdf_helpers.py desktop_app/src/autoreview_app/extract/base.py desktop_app/src/autoreview_app/extract/pymupdf_extractor.py desktop_app/tests/test_pymupdf_extractor.py
git commit -m "feat(desktop): PyMuPDF extractor emits Docling JSON"
```

---

### Task 4: `allocate_paper_id` — next free Sxx id

**Files:**
- Create: `desktop_app/src/autoreview_app/paper_ids.py`
- Test: `desktop_app/tests/test_paper_ids.py`

- [ ] **Step 1: Write the failing tests.** Create `desktop_app/tests/test_paper_ids.py`:

```python
from pathlib import Path

from autoreview_app.paper_ids import allocate_paper_id


def test_empty_or_missing_library_starts_at_s1(tmp_path: Path):
    assert allocate_paper_id(tmp_path) == "S1"
    assert allocate_paper_id(tmp_path / "nope") == "S1"


def test_next_after_max_existing(tmp_path: Path):
    (tmp_path / "S05").mkdir()
    (tmp_path / "S290").mkdir()
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".cache").mkdir()
    assert allocate_paper_id(tmp_path) == "S291"


def test_ignores_non_matching_dir_names(tmp_path: Path):
    (tmp_path / "S12").mkdir()
    (tmp_path / "Sxx").mkdir()
    (tmp_path / "S12abc").mkdir()
    assert allocate_paper_id(tmp_path) == "S13"
```

- [ ] **Step 2: Run to verify they fail.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_paper_ids.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.paper_ids'`.

- [ ] **Step 3: Implement.** Create `desktop_app/src/autoreview_app/paper_ids.py`:

```python
from __future__ import annotations

import re
from pathlib import Path

_PAPER_DIR = re.compile(r"^S(\d+)$")


def allocate_paper_id(library_dir: Path) -> str:
    """Return the next free paper id ("S<n>") above the max existing Sxx dir.

    The engine derives a paper id from the Docling JSON filename stem, so this
    only needs to be unique within the library directory. Empty/missing -> "S1".
    """
    max_n = 0
    if library_dir.is_dir():
        for child in library_dir.iterdir():
            if not child.is_dir():
                continue
            match = _PAPER_DIR.fullmatch(child.name)
            if match:
                max_n = max(max_n, int(match.group(1)))
    return f"S{max_n + 1}"
```

- [ ] **Step 4: Run to verify they pass.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_paper_ids.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/paper_ids.py desktop_app/tests/test_paper_ids.py
git commit -m "feat(desktop): allocate next Sxx paper id"
```

---

### Task 5: `build_package_from_pdf` — end-to-end PDF → clean package (contract test)

**Files:**
- Modify: `desktop_app/src/autoreview_app/engine_bridge.py`
- Test: `desktop_app/tests/test_engine_bridge.py`

- [ ] **Step 1: Write the failing contract test.** Create `desktop_app/tests/test_engine_bridge.py`:

```python
import json
from pathlib import Path

from _pdf_helpers import make_pdf

from autoreview_app.engine_bridge import build_package_from_pdf
from autoreview_app.extract.pymupdf_extractor import PyMuPDFExtractor
from autoreview_app.library_index import list_papers


def test_pdf_becomes_a_valid_clean_package(tmp_path: Path):
    pdf = make_pdf(tmp_path / "mypaper.pdf", ["Hello abstract world.", "Methods section here."])
    library = tmp_path / "library"
    docling_dir = tmp_path / "docling_json"

    paper_id = build_package_from_pdf(
        pdf_path=pdf,
        library_dir=library,
        docling_json_dir=docling_dir,
        extractor=PyMuPDFExtractor(),
    )

    assert paper_id == "S1"
    paper_dir = library / paper_id

    # The engine produced its clean-package files.
    content = json.loads((paper_dir / "content_blocks.json").read_text(encoding="utf-8"))
    assert content["paper_id"] == "S1"
    blocks_text = " ".join(b.get("text", "") for b in content["blocks"])
    assert "Hello abstract world." in blocks_text

    assert (paper_dir / "evidence.json").exists()
    assert (paper_dir / "metadata_candidates.json").exists()
    assert (paper_dir / "content.md").read_text(encoding="utf-8").strip()

    # The new paper is now visible to the library lister from M1.
    assert list_papers(library) == ["S1"]


def test_second_import_gets_next_id(tmp_path: Path):
    library = tmp_path / "library"
    docling_dir = tmp_path / "docling_json"
    first = make_pdf(tmp_path / "a.pdf", ["First paper text."])
    second = make_pdf(tmp_path / "b.pdf", ["Second paper text."])

    id1 = build_package_from_pdf(pdf_path=first, library_dir=library, docling_json_dir=docling_dir, extractor=PyMuPDFExtractor())
    id2 = build_package_from_pdf(pdf_path=second, library_dir=library, docling_json_dir=docling_dir, extractor=PyMuPDFExtractor())

    assert id1 == "S1"
    assert id2 == "S2"
```

- [ ] **Step 2: Run to verify it fails.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_engine_bridge.py -v
```

Expected: FAIL — `build_package_from_pdf` raises `NotImplementedError` (placeholder from Task 1).

- [ ] **Step 3: Implement `build_package_from_pdf`.** Edit `desktop_app/src/autoreview_app/engine_bridge.py`. Replace the entire file with:

```python
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Protocol

# engine_bridge.py lives at desktop_app/src/autoreview_app/engine_bridge.py.
# parents[3] is the repo root; the engine source is Document_Decomposer/src.
ENGINE_SRC = Path(__file__).resolve().parents[3] / "Document_Decomposer" / "src"
if not ENGINE_SRC.is_dir():
    raise RuntimeError(
        f"Engine source not found at {ENGINE_SRC}; expected Document_Decomposer/src"
    )
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from docdecomp.package_builder import build_clean_package  # noqa: E402

from .paper_ids import allocate_paper_id


class _Extractor(Protocol):
    name: str

    def extract(self, pdf_path: Path) -> dict[str, Any]:
        ...


def _slug(stem: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    return cleaned[:40].strip("_") or "paper"


def build_package_from_pdf(
    pdf_path: Path,
    library_dir: Path,
    docling_json_dir: Path,
    extractor: _Extractor,
) -> str:
    """PDF -> Docling JSON (via extractor) -> engine clean package. Returns paper id.

    The engine derives the paper id from the JSON filename stem, so the file is
    named "<paper_id>_<slug>.json". Fully offline; no AI.
    """
    paper_id = allocate_paper_id(library_dir)
    docling = extractor.extract(pdf_path)

    docling_json_dir.mkdir(parents=True, exist_ok=True)
    json_path = docling_json_dir / f"{paper_id}_{_slug(pdf_path.stem)}.json"
    json_path.write_text(json.dumps(docling, ensure_ascii=False), encoding="utf-8")

    result = build_clean_package(json_path, None, library_dir)
    return result.paper_id
```

- [ ] **Step 4: Run the contract test to verify it passes.** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_engine_bridge.py -v
```

Expected: PASS (2 passed). If `content["blocks"]` is empty (no text survived), STOP and report — it likely means the synthesized PDF's text was dropped as "furniture"/noise by the engine; report the actual `content_blocks.json` contents.

- [ ] **Step 5: Run the FULL suite (M1 + M2a).** Run (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -q
```

Expected: all green — the 15 M1 tests plus the M2a tests (engine_bridge_import 1 + docling_json 4 + pymupdf_extractor 3 + paper_ids 3 + engine_bridge 2 = 28 total). A httpx/starlette deprecation warning is acceptable.

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/src/autoreview_app/engine_bridge.py desktop_app/tests/test_engine_bridge.py
git commit -m "feat(desktop): PDF to clean package via PyMuPDF + engine (offline)"
```

---

## Done criteria for M2a

- A PDF runs entirely offline through `PyMuPDFExtractor` → minimal Docling JSON → engine `build_clean_package` → a valid `library/Sxx/` clean package (`content_blocks.json` with real text, `evidence.json`, `metadata_candidates.json`, `content.md`).
- `allocate_paper_id` assigns sequential `Sxx` ids; second import gets the next id.
- `list_papers` (from M1) sees the imported paper.
- Full suite green (~28 tests). Work committed on `feat/desktop-app-m2a`; not pushed.

## Out of scope for M2a (next: M2b)

- The AI stages (`sections` → `reading` → `card`) that turn the clean package into a literature card — these need live DeepSeek (or dry-run/mocked) and are M2b.
- The async job runner + `POST /papers/import` HTTP endpoint — M2b.
- Docling as a second `PdfExtractor` implementation (optional plugin) — later.
- Figures/tables extraction via PyMuPDF (M2a emits text only; engine tolerates empty pictures/tables) — later if needed.

---

## Self-review (done by the planner)

- **Coverage vs M2a slice of the roadmap (§ "M2 Extraction slot", first half):** pinned clean-package contract (Task 1/engine note), `ExtractorPlugin` interface (Task 3 `base.PdfExtractor`), PyMuPDF implementation (Task 3), contract test that engine consumes it (Task 5), paper-id allocation (Task 4). The AI half and the import endpoint are explicitly deferred to M2b. ✓
- **Placeholders:** none — every step has full code and exact commands. The Task 1 placeholder `build_package_from_pdf` is intentional and is fully replaced in Task 5 Step 3 (whole-file rewrite), so no dangling stub remains. ✓
- **Type/name consistency:** `build_docling_json(name, origin_filename, text_items)` defined in Task 2 and called identically in Task 3. `PyMuPDFExtractor.name == "pymupdf"` and `.extract(pdf_path)->dict` match the `PdfExtractor` Protocol and the `_Extractor` Protocol used by `build_package_from_pdf`. `allocate_paper_id(library_dir)` defined in Task 4, used in Task 5. `list_papers` is the existing M1 function. `build_clean_package(json_path, md_path, output_root, ...)` matches the verified engine signature (called as `build_clean_package(json_path, None, library_dir)`). ✓
