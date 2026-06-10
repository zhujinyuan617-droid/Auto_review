# Desktop App M6a — Writing quality gates (citation + style)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the engine's mechanical writing gates — the checks that stop "AI slop" (bare/parenthetical `Sxx` citations, adjacent citation blocks, citation-as-subject, plus style red-flags like "more research is needed") — as a desktop capability: `check_draft(text)` and `POST /writing/check`. This is the highest-value, lowest-friction slice of the writing assistant (pure functions, no AI, fully testable), and it establishes the engine write-path bridge that the full author/expert loop (M6b) will reuse.

**Architecture:** The engine's gate functions live at module level in `Document_Decomposer/scripts/write/run_writing_loop.py` — `citation_gate(draft_text) -> dict` and `style_gate(draft_text) -> dict` are pure (regex only, no I/O, no AI, no class). The desktop app adds a lazy write-path bridge (`engine_bridge.ensure_engine_write_on_path()`), a thin `writing/gates.py` that imports and composes those two gates into `check_draft(text)`, and a `POST /writing/check` route. No AI, no network — fully offline-testable.

**Tech Stack:** Python 3.12 (`desktop_app/.venv`), the engine `run_writing_loop` module (stdlib-based), FastAPI, pytest. No new deps.

**Git:** branch `feat/desktop-app-m6a`; commit per task; no push; user merges after review.

**Depends on:** M1 (app), M2b (`engine_bridge` with `ensure_engine_scripts_on_path` pattern). Run from `desktop_app/` with `.venv\Scripts\python`.

---

## Verified facts (from engine source — do not re-derive)

- `Document_Decomposer/scripts/write/run_writing_loop.py` defines module-level pure functions:
  - `citation_gate(draft_text: str) -> dict` — returns `{"passed": bool, "bare_paper_ids": [...], "parenthetical_citation_groups": [...], "adjacent_bracketed_citation_groups": [...], "citation_subject_groups": [...]}`. Passes only when all four lists are empty. Flags: bare `Sxx` in prose; `(Sxx ...)`; `[S09][S108]` adjacency; `[Sxx] reports/shows/...` subject use.
  - `style_gate(draft_text: str) -> dict` — returns `{"passed": True, "warnings": [...]}` (always non-fatal); flags 8 patterns incl. "more/further research is needed", scope-defense, self-promotion, "it is important to note that".
  - These take a bare string, do only regex, return a plain dict. No file I/O, no AI, no config.
- `evidence_gate`/`completeness_gate` need a `brief` dict — deferred to M6b (they belong with brief construction).
- The engine write dir is `Document_Decomposer/scripts/write/`. `run_writing_loop.py` is importable (stdlib + docdecomp); importing it must not run `main()` (guarded by `if __name__ == "__main__"`).
- `engine_bridge.py` (M2a/M2b) already computes `ENGINE_SRC` and has a lazy `ensure_engine_scripts_on_path()`. M6a adds a parallel `ensure_engine_write_on_path()` for `scripts/write/`.

---

## File Structure (all under `desktop_app/`)

- `src/autoreview_app/engine_bridge.py` — MODIFY: add `ENGINE_WRITE` + `ensure_engine_write_on_path()`
- `src/autoreview_app/writing/__init__.py`
- `src/autoreview_app/writing/gates.py` — `check_draft(draft_text) -> dict`
- `src/autoreview_app/api.py` — MODIFY: `POST /writing/check`
- Tests: `tests/test_writing_gates.py`, `tests/test_api_writing_check.py`

Boundaries: `engine_bridge` owns the path wiring; `writing/gates` composes the engine gates; `api` wires HTTP. Offline, no AI.

---

### Task 1: Write-path bridge + gate wrapper

**Files:**
- Modify: `desktop_app/src/autoreview_app/engine_bridge.py`
- Create: `desktop_app/src/autoreview_app/writing/__init__.py`
- Create: `desktop_app/src/autoreview_app/writing/gates.py`
- Test: `desktop_app/tests/test_writing_gates.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_writing_gates.py`:

```python
from autoreview_app.writing.gates import check_draft


def test_clean_draft_passes_citation_gate():
    draft = "Methane adsorption increases with pressure [S09]. Carbon capture follows [S12]."
    result = check_draft(draft)
    assert result["citation"]["passed"] is True


def test_bare_paper_id_fails_citation_gate():
    draft = "Methane adsorption increases with pressure S09."
    result = check_draft(draft)
    assert result["citation"]["passed"] is False
    assert "S09" in " ".join(result["citation"]["bare_paper_ids"]) or result["citation"]["bare_paper_ids"]


def test_adjacent_citation_blocks_fail():
    draft = "This is supported by multiple works [S09][S108]."
    result = check_draft(draft)
    assert result["citation"]["passed"] is False
    assert result["citation"]["adjacent_bracketed_citation_groups"]


def test_style_gate_flags_generic_research_needed():
    draft = "More research is needed to understand this fully."
    result = check_draft(draft)
    # style gate is non-fatal but must surface the warning
    assert result["style"]["warnings"]


def test_clean_draft_has_no_style_warnings():
    draft = "Methane adsorption increases with pressure [S09]."
    result = check_draft(draft)
    assert result["style"]["warnings"] == []
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_writing_gates.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.writing'`.

- [ ] **Step 3: Add the write-path bridge.** In `desktop_app/src/autoreview_app/engine_bridge.py`, after the existing `ensure_engine_scripts_on_path` function, add:

```python
ENGINE_WRITE = ENGINE_SRC.parent / "scripts" / "write"


def ensure_engine_write_on_path() -> None:
    """Put the engine's scripts/write dir on sys.path (lazy; only writing code needs it)."""
    if not ENGINE_WRITE.is_dir():
        raise RuntimeError(
            f"Engine write scripts not found at {ENGINE_WRITE}; expected Document_Decomposer/scripts/write"
        )
    if str(ENGINE_WRITE) not in sys.path:
        sys.path.insert(0, str(ENGINE_WRITE))
```

(Leave the rest of `engine_bridge.py` unchanged.)

- [ ] **Step 4: Create the writing subpackage marker** — `desktop_app/src/autoreview_app/writing/__init__.py`:

```python
"""Writing assistant: quality gates now; author/expert loop + ideation later."""
```

- [ ] **Step 5: Implement the gate wrapper** — `desktop_app/src/autoreview_app/writing/gates.py`:

```python
from __future__ import annotations

from typing import Any

from .. import engine_bridge

engine_bridge.ensure_engine_write_on_path()  # adds Document_Decomposer/scripts/write to sys.path

import run_writing_loop as _writing_loop  # engine module (now importable)  # noqa: E402


def check_draft(draft_text: str) -> dict[str, Any]:
    """Run the engine's mechanical citation gate + style gate on a draft string.

    Pure: no AI, no file I/O. Returns {"citation": {...}, "style": {...}} where
    citation.passed is the hard gate and style.warnings is advisory (non-fatal).
    """
    return {
        "citation": _writing_loop.citation_gate(draft_text),
        "style": _writing_loop.style_gate(draft_text),
    }
```

- [ ] **Step 6: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_writing_gates.py -v
```

Expected: PASS (5 passed). If importing `run_writing_loop` fails (e.g. it has a heavy top-level import or runs work at import time), STOP and report the exact traceback — do NOT modify the engine.

- [ ] **Step 7: Commit.**

```powershell
git checkout -b feat/desktop-app-m6a
git add desktop_app/src/autoreview_app/engine_bridge.py desktop_app/src/autoreview_app/writing/__init__.py desktop_app/src/autoreview_app/writing/gates.py desktop_app/tests/test_writing_gates.py
git commit -m "feat(desktop): wrap engine citation+style gates (check_draft)"
```

---

### Task 2: `POST /writing/check` endpoint

**Files:**
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api_writing_check.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_api_writing_check.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(tmp_path: Path):
    return TestClient(create_app(AppConfig(library_dir=tmp_path / "library")))


def test_check_clean_draft(tmp_path: Path):
    resp = _client(tmp_path).post("/writing/check", json={"draft": "Adsorption rises [S09]."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["citation"]["passed"] is True
    assert body["style"]["warnings"] == []


def test_check_flags_bare_citation(tmp_path: Path):
    resp = _client(tmp_path).post("/writing/check", json={"draft": "Adsorption rises S09."})
    assert resp.status_code == 200
    assert resp.json()["citation"]["passed"] is False
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_writing_check.py -v
```

Expected: FAIL — no `/writing/check` route (404).

- [ ] **Step 3: Add the route.** In `desktop_app/src/autoreview_app/api.py`, add the import near the other local imports:

```python
from .writing.gates import check_draft
```

Add a request model near the others (e.g. next to `ImportRequest`):

```python
class DraftCheckRequest(BaseModel):
    draft: str
```

Inside `create_app`, before `return app`, add:

```python
    @app.post("/writing/check")
    def writing_check(req: DraftCheckRequest) -> dict[str, Any]:
        return check_draft(req.draft)
```

(Leave existing routes unchanged. `Any` and `BaseModel` are already imported in api.py.)

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_writing_check.py -v
```

Expected: PASS (2 passed).

- [ ] **Step 5: Run the FULL suite** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -q
```

Expected: all green. Report the summary line.

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api_writing_check.py
git commit -m "feat(desktop): POST /writing/check runs the mechanical gates"
```

---

## Done criteria for M6a

- `engine_bridge.ensure_engine_write_on_path()` lazily exposes `scripts/write`.
- `check_draft(text)` runs the engine's real `citation_gate` + `style_gate` and returns both.
- `POST /writing/check` returns the gate results for a posted draft.
- Full suite green. Branch `feat/desktop-app-m6a`; not pushed.

## Out of scope for M6a (next: M6b, M6c)

- **M6b — the author/expert/adjudicator loop:** wrap one writing round (build brief → author AI → mechanical_gates → 4 expert reviews → adjudicator) with an injected fake client (the engine functions take `client` explicitly; 6 AI calls/round). Needs a brief (the loop builds it via subprocess; `build_writing_brief.build_brief(args)` is importable to bypass that). + `evidence_gate`/`completeness_gate` (need the brief). A writing session/draft endpoint.
- **M6c — ideation/interrogation:** wrap `scripts/use/propose_angles.py`'s importable `build_candidates(edges, cidx)` + AI ranking; the user-refinement loop; feed the agreed angle into M6b.
- A real-AI end-to-end writing smoke (manual; needs the user's config + edges/concept_index/cards).

---

## Self-review (planner)

- **Coverage vs design §5.6 (writing screen, gates portion) + repo writing constraints:** the mechanical citation gate + style gate (the "no AI slop" guardrails) are exposed; the full interrogation→draft→expert loop is M6b/M6c. ✓
- **Placeholders:** none — full code/commands per step. The one risk (importing `run_writing_loop`) is flagged with an explicit STOP-and-report. ✓
- **Type/name consistency:** `ensure_engine_write_on_path()` (Task 1) mirrors the existing `ensure_engine_scripts_on_path()`; `check_draft(text)` (Task 1) used by the endpoint (Task 2). `DraftCheckRequest` next to existing models. `create_app` signature unchanged. ✓
