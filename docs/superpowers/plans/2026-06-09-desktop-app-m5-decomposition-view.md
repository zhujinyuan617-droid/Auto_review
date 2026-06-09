# Desktop App M5 — Single-paper decomposition view

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Assemble a paper's fine-layer artifacts into a structured "decomposition" payload for the single-paper reader: abstract points, intro problems, glossary, analyses (method atoms), results (result atoms), and result-relations (intra-paper syntheses) — each item carrying its source anchor for click-to-trace — exposed as `GET /papers/{id}/decomposition`.

**Architecture:** Pure assembly over JSON already on disk. The engine produces `reading_blocks.json`, `literature_card.json`, `evidence_atoms.json`, `paper_syntheses.json` per paper (261/264 of the existing library already have the fine layer). `decomposition.py` reads those (each optional — degrade gracefully if absent), filters/maps them into the view payload, and attaches trace anchors: atoms carry `reading_block_id`; syntheses link to atoms via `supporting_evidence_atom_ids`. The endpoint reads the paper dir and 404s if the paper doesn't exist. Producing the fine layer + a glossary for newly-imported papers is a follow-up (M5b); this milestone delivers the view over existing data and tolerates missing pieces.

**Tech Stack:** Python 3.12 (`desktop_app/.venv`), stdlib `json`, FastAPI, pytest. No new deps, no AI, no network.

**Git:** branch `feat/desktop-app-m5`; commit per task; no push; user merges after review.

**Depends on:** M1 (app), M4a (library/paper dirs). Run from `desktop_app/` with `.venv\Scripts\python`.

---

## Verified facts (from engine source/artifacts — do not re-derive)

- `reading_blocks.json`: `{..., reading_blocks: [{reading_block_id, section_kind, section_title, reading_type, text, page_start, page_end, ...}]}`. `section_kind` ∈ {abstract, introduction, methods, results, ...}. Abstract/intro text is read directly (no AI).
- `evidence_atoms.json`: `{schema_version, paper_id, evidence_atoms: [{evidence_atom_id, atom_type, quote, minimal_claim, reading_block_id, source_block_ids, page_start, page_end, topic_tags, confidence}]}`. `atom_type` ∈ {method, variable, mechanism, result, quantitative_result, limitation, scope, background, other}. **`reading_block_id` is the click-to-source anchor.**
- `paper_syntheses.json`: `{schema_version, paper_id, paper_syntheses: [{synthesis_id, synthesis_type, claim, supporting_evidence_atom_ids, reasoning, scope, confidence, limitations}]}`. `synthesis_type` ∈ {method_result_link, mechanism_result_link, variable_effect, limitation_scope, evidence_summary, other}. Syntheses trace to source via atoms (two-hop: synthesis → atom → reading_block).
- `literature_card.json`: slim card with `paper:{title,...}`, `summary:{objective, main_findings, ...}`.
- `glossary.json` does NOT exist anywhere yet — the assembler treats it as optional (empty if absent); building glossary extraction is deferred.
- 3 early papers (e.g. S02) lack the fine layer — the assembler must degrade (empty analyses/results/relations), not error.

---

## File Structure (all under `desktop_app/`)

- `src/autoreview_app/decomposition.py` — `assemble_decomposition(paper_dir) -> dict`
- `src/autoreview_app/api.py` — MODIFY: `GET /papers/{paper_id}/decomposition`
- Tests: `tests/test_decomposition.py`, `tests/test_api_decomposition.py`, plus fine-layer fixture helpers added to `tests/_library_fixtures.py`

Boundaries: `decomposition` is a pure reader/assembler; `api` wires. Both testable offline with JSON fixtures.

---

### Task 1: Decomposition assembler

**Files:**
- Modify: `desktop_app/tests/_library_fixtures.py` (add fine-layer fixture writers)
- Create: `desktop_app/src/autoreview_app/decomposition.py`
- Test: `desktop_app/tests/test_decomposition.py`

- [ ] **Step 1: Add fine-layer fixture writers.** Append to `desktop_app/tests/_library_fixtures.py`:

```python
def write_reading_blocks(library: Path, paper_id: str, blocks: list[dict]) -> None:
    paper_dir = library / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "0.1.0", "paper_id": paper_id, "reading_blocks": blocks}
    (paper_dir / "reading_blocks.json").write_text(json.dumps(doc), encoding="utf-8")


def write_evidence_atoms(library: Path, paper_id: str, atoms: list[dict]) -> None:
    paper_dir = library / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "0.1.0", "paper_id": paper_id, "evidence_atoms": atoms}
    (paper_dir / "evidence_atoms.json").write_text(json.dumps(doc), encoding="utf-8")


def write_paper_syntheses(library: Path, paper_id: str, syntheses: list[dict]) -> None:
    paper_dir = library / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "0.1.0", "paper_id": paper_id, "paper_syntheses": syntheses}
    (paper_dir / "paper_syntheses.json").write_text(json.dumps(doc), encoding="utf-8")


def write_glossary(library: Path, paper_id: str, terms: list[dict]) -> None:
    paper_dir = library / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    doc = {"schema_version": "0.1.0", "paper_id": paper_id, "glossary": terms}
    (paper_dir / "glossary.json").write_text(json.dumps(doc), encoding="utf-8")
```

- [ ] **Step 2: Write the failing tests** — `desktop_app/tests/test_decomposition.py`:

```python
from pathlib import Path

from _library_fixtures import (
    write_card,
    write_evidence_atoms,
    write_glossary,
    write_paper_syntheses,
    write_reading_blocks,
)

from autoreview_app.decomposition import assemble_decomposition


def _full_paper(library: Path) -> Path:
    pid = "S1"
    write_card(library, pid, title="Methane Study", doi="10.1/a", findings=["Adsorption rises."])
    write_reading_blocks(library, pid, [
        {"reading_block_id": "S1-RB-0001", "section_kind": "abstract", "text": "We study methane."},
        {"reading_block_id": "S1-RB-0002", "section_kind": "introduction", "text": "The problem is X."},
        {"reading_block_id": "S1-RB-0003", "section_kind": "methods", "text": "We used GCMC."},
    ])
    write_evidence_atoms(library, pid, [
        {"evidence_atom_id": "S1-EVATOM-0001", "atom_type": "method", "minimal_claim": "GCMC simulation", "quote": "We used GCMC.", "reading_block_id": "S1-RB-0003", "confidence": "high"},
        {"evidence_atom_id": "S1-EVATOM-0002", "atom_type": "result", "minimal_claim": "Adsorption rises", "quote": "rises", "reading_block_id": "S1-RB-0003", "confidence": "medium"},
        {"evidence_atom_id": "S1-EVATOM-0003", "atom_type": "quantitative_result", "minimal_claim": "12 mmol/g", "quote": "12", "reading_block_id": "S1-RB-0003", "confidence": "high"},
        {"evidence_atom_id": "S1-EVATOM-0004", "atom_type": "background", "minimal_claim": "context", "quote": "x", "reading_block_id": "S1-RB-0002", "confidence": "low"},
    ])
    write_paper_syntheses(library, pid, [
        {"synthesis_id": "S1-SYN-0001", "synthesis_type": "method_result_link", "claim": "GCMC shows adsorption rises", "supporting_evidence_atom_ids": ["S1-EVATOM-0001", "S1-EVATOM-0002"]},
    ])
    write_glossary(library, pid, [
        {"term": "GCMC", "definition": "Grand Canonical Monte Carlo", "reading_block_id": "S1-RB-0003"},
    ])
    return library / pid


def test_assembles_all_sections(tmp_path: Path):
    paper_dir = _full_paper(tmp_path / "library")
    view = assemble_decomposition(paper_dir)

    assert view["paper_id"] == "S1"
    assert view["card"]["title"] == "Methane Study"
    assert [b["text"] for b in view["abstract_blocks"]] == ["We study methane."]
    assert [b["reading_block_id"] for b in view["intro_blocks"]] == ["S1-RB-0002"]
    assert view["glossary"][0]["term"] == "GCMC"

    # analyses = method/variable/mechanism atoms; results = result/quantitative_result
    assert {a["evidence_atom_id"] for a in view["analyses"]} == {"S1-EVATOM-0001"}
    assert {a["evidence_atom_id"] for a in view["results"]} == {"S1-EVATOM-0002", "S1-EVATOM-0003"}
    # every analysis/result carries its source anchor
    assert all("reading_block_id" in a for a in view["analyses"] + view["results"])

    assert view["result_relations"][0]["synthesis_id"] == "S1-SYN-0001"
    assert view["result_relations"][0]["supporting_evidence_atom_ids"] == ["S1-EVATOM-0001", "S1-EVATOM-0002"]


def test_missing_fine_layer_degrades_gracefully(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S9", title="Bare", doi="")  # card only, no reading/atoms/syntheses/glossary
    view = assemble_decomposition(library / "S9")

    assert view["paper_id"] == "S9"
    assert view["card"]["title"] == "Bare"
    assert view["abstract_blocks"] == []
    assert view["intro_blocks"] == []
    assert view["glossary"] == []
    assert view["analyses"] == []
    assert view["results"] == []
    assert view["result_relations"] == []


def test_paper_id_falls_back_to_dirname(tmp_path: Path):
    library = tmp_path / "library"
    (library / "S7").mkdir(parents=True)  # totally empty paper dir
    view = assemble_decomposition(library / "S7")
    assert view["paper_id"] == "S7"
```

- [ ] **Step 3: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_decomposition.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.decomposition'`.

- [ ] **Step 4: Implement** — `desktop_app/src/autoreview_app/decomposition.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

# Atom types shown under "analyses" vs "results".
_ANALYSIS_TYPES = {"method", "variable", "mechanism"}
_RESULT_TYPES = {"result", "quantitative_result"}


def _read(paper_dir: Path, name: str) -> dict[str, Any]:
    path = paper_dir / name
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _blocks_of_kind(reading: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    out = []
    for block in reading.get("reading_blocks") or []:
        if block.get("section_kind") == kind:
            out.append({"reading_block_id": block.get("reading_block_id"), "text": block.get("text", "")})
    return out


def _atom_view(atom: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidence_atom_id": atom.get("evidence_atom_id"),
        "atom_type": atom.get("atom_type"),
        "minimal_claim": atom.get("minimal_claim", ""),
        "quote": atom.get("quote", ""),
        "reading_block_id": atom.get("reading_block_id"),  # click-to-source anchor
        "confidence": atom.get("confidence"),
    }


def assemble_decomposition(paper_dir: Path) -> dict[str, Any]:
    """Assemble the single-paper decomposition payload from on-disk artifacts.

    Each artifact is optional; missing ones degrade to empty sections. Atoms carry
    a reading_block_id source anchor; syntheses trace via supporting atom ids.
    """
    card = _read(paper_dir, "literature_card.json")
    reading = _read(paper_dir, "reading_blocks.json")
    atoms_doc = _read(paper_dir, "evidence_atoms.json")
    syn_doc = _read(paper_dir, "paper_syntheses.json")
    glossary_doc = _read(paper_dir, "glossary.json")

    paper_id = card.get("paper_id") or reading.get("paper_id") or paper_dir.name
    paper = card.get("paper") or {}
    summary = card.get("summary") or {}

    atoms = atoms_doc.get("evidence_atoms") or []
    analyses = [_atom_view(a) for a in atoms if a.get("atom_type") in _ANALYSIS_TYPES]
    results = [_atom_view(a) for a in atoms if a.get("atom_type") in _RESULT_TYPES]

    relations = []
    for syn in syn_doc.get("paper_syntheses") or []:
        relations.append({
            "synthesis_id": syn.get("synthesis_id"),
            "synthesis_type": syn.get("synthesis_type"),
            "claim": syn.get("claim", ""),
            "supporting_evidence_atom_ids": syn.get("supporting_evidence_atom_ids") or [],
        })

    return {
        "paper_id": paper_id,
        "card": {
            "title": paper.get("title", ""),
            "year": str(paper.get("year", "")),
            "journal": paper.get("journal", ""),
            "objective": summary.get("objective", ""),
            "main_findings": summary.get("main_findings") or [],
        },
        "abstract_blocks": _blocks_of_kind(reading, "abstract"),
        "intro_blocks": _blocks_of_kind(reading, "introduction"),
        "glossary": glossary_doc.get("glossary") or [],
        "analyses": analyses,
        "results": results,
        "result_relations": relations,
    }
```

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_decomposition.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 6: Commit.**

```powershell
git checkout -b feat/desktop-app-m5
git add desktop_app/tests/_library_fixtures.py desktop_app/src/autoreview_app/decomposition.py desktop_app/tests/test_decomposition.py
git commit -m "feat(desktop): assemble single-paper decomposition from fine-layer JSON"
```

---

### Task 2: `GET /papers/{paper_id}/decomposition` endpoint

**Files:**
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api_decomposition.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_api_decomposition.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from _library_fixtures import write_card, write_reading_blocks

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(library: Path):
    return TestClient(create_app(AppConfig(library_dir=library)))


def test_decomposition_endpoint(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="Methane Study", doi="10.1/a")
    write_reading_blocks(library, "S1", [
        {"reading_block_id": "S1-RB-0001", "section_kind": "abstract", "text": "We study methane."},
    ])

    resp = _client(library).get("/papers/S1/decomposition")
    assert resp.status_code == 200
    body = resp.json()
    assert body["paper_id"] == "S1"
    assert body["card"]["title"] == "Methane Study"
    assert body["abstract_blocks"][0]["text"] == "We study methane."


def test_decomposition_unknown_paper_404(tmp_path: Path):
    library = tmp_path / "library"
    write_card(library, "S1", title="X")
    assert _client(library).get("/papers/missing/decomposition").status_code == 404
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_decomposition.py -v
```

Expected: FAIL — no `/papers/{id}/decomposition` route (404 for the valid paper too, or the assert on body fails).

- [ ] **Step 3: Add the route.** In `desktop_app/src/autoreview_app/api.py`, add the import near the other local imports:

```python
from .decomposition import assemble_decomposition
```

Inside `create_app`, before `return app`, add (note: register this BEFORE the existing `GET /papers/{paper_id}` is fine — FastAPI matches the more specific literal path `/papers/{id}/decomposition` distinctly):

```python
    @app.get("/papers/{paper_id}/decomposition")
    def paper_decomposition(paper_id: str) -> dict[str, Any]:
        paper_dir = config.library_dir / paper_id
        if not paper_dir.is_dir():
            raise HTTPException(status_code=404, detail="unknown paper")
        return assemble_decomposition(paper_dir)
```

(Leave existing routes unchanged.)

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_decomposition.py -v
```

Expected: PASS (2 passed). Then confirm no regression on the existing paper route: `.venv\Scripts\python -m pytest tests/test_api_browse.py -v` → 4 passed.

- [ ] **Step 5: Run the FULL suite** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -q
```

Expected: all green. Report the summary line.

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api_decomposition.py
git commit -m "feat(desktop): GET /papers/{id}/decomposition endpoint"
```

---

## Done criteria for M5

- `assemble_decomposition(paper_dir)` reads the fine-layer JSON (each optional) into a structured view: card, abstract/intro blocks, glossary, analyses (method-ish atoms), results (result atoms), result-relations (syntheses) — each item with its source anchor.
- Missing artifacts degrade to empty sections (no error); paper_id falls back to the dir name.
- `GET /papers/{id}/decomposition` returns the payload (404 for unknown paper).
- Full suite green. Branch `feat/desktop-app-m5`; not pushed.

## Out of scope for M5 (next: M5b)

- **Producing the fine layer for newly-imported papers** — extend the desktop AI pipeline (`ai/stages.py`) with evidence-atoms + paper-syntheses stages reusing `evidence_synthesis.py` (importable build/ensure/validate functions, injected client — same pattern as M2b). The existing library already has these artifacts; new imports need the stages.
- **Glossary extraction** — a brand-new `build_glossary_prompt`/`ensure`/`validate` module (none exists); the assembler already tolerates its absence.
- **Frontend reader screen** with click-to-source jumps — the backend payload (with anchors) lands here; the visual UI is a frontend pass.

---

## Self-review (planner)

- **Coverage vs design §5C:** abstract points + intro problems (from reading_blocks), glossary (optional), analyses→results (method vs result atoms), result-relations (syntheses), each with source anchor (atom reading_block_id; synthesis atom ids). The view is assembled from existing artifacts; producing the fine layer + glossary for new imports is explicitly deferred to M5b. ✓
- **Placeholders:** none — full code/commands per step. ✓
- **Type/name consistency:** `assemble_decomposition(paper_dir)` (Task 1) used by the endpoint (Task 2). Fixture writers (`write_reading_blocks/evidence_atoms/paper_syntheses/glossary`) added to `_library_fixtures.py` alongside the existing `write_card`. The endpoint uses `config.library_dir` + `HTTPException` (already imported in api.py). Route `/papers/{id}/decomposition` is distinct from the existing `/papers/{id}`. ✓
