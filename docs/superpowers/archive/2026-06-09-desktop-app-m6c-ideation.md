# Desktop App M6c — Ideation (candidate writing angles from the relation graph)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface candidate writing angles from the relation graph + concept index — tensions (contradicting papers), gaps (specific concepts widely invoked but studied by few), and synthesis clusters (papers richly connected by complements) — so the user has somewhere to start interrogating. Exposed as `GET /writing/angles`. Deterministic and fully offline.

**Architecture:** The engine's `scripts/use/propose_angles.py` has a pure, importable `build_candidates(edges, cidx, n_each=10) -> {"tension", "gaps", "synthesis"}` that derives candidates from the edge list (contradicts → tension) and the concept index (gap/synthesis scoring). The desktop adds a lazy `ensure_engine_use_on_path()` bridge, a `writing/ideation.py` that wraps `build_candidates` and loads `edges.json` + `concept_index.json` from disk (graceful empties if absent), and a `GET /writing/angles` route. The AI ranking/phrasing step (the engine's `SYSTEM` prompt) is deferred — M6c ships the deterministic candidate seed.

**Tech Stack:** Python 3.12 (`desktop_app/.venv`), the engine `propose_angles` module, FastAPI, pytest. No new deps, no AI, no network.

**Git:** branch `feat/desktop-app-m6c`; commit per task; no push; user merges after review.

**Depends on:** M4a (`AppConfig.edges_path`, the `/network` edges reader), M6a (`ensure_engine_*_on_path` pattern). Run from `desktop_app/` with `.venv\Scripts\python`.

---

## Verified facts (from `propose_angles.py` — do not re-derive)

- `build_candidates(edges, cidx, n_each=10) -> {"tension": [...], "gaps": [...], "synthesis": [...]}` is pure (stdlib only):
  - **tension**: one entry per `edge` with `relation == "contradicts"` → `{a, b, shared, why=edge["rationale"]}`. Reads `edge["a"], edge["b"], edge["shared"], edge["rationale"]`.
  - **gaps**: concepts `c` in `cidx` where `d.get("specific")` AND `d["n_central"] >= 1` AND `d["n_passing"] >= 5` → `{concept, n_central, n_passing, central, gap_score}`; sorted by `gap_score` desc, top `n_each`.
  - **synthesis**: concepts with >=2 central whose members are connected by `complements` edges; member set = `set(d["central"]) | {p["paper"] for p in d["passing"]}`.
- `edges` is the EDGE LIST (the `edges.json` `"edges"` array), not the wrapper dict. `cidx` is the concept-index dict `{concept: {n_central, n_passing, central, passing, gap_score, specific}}`.
- The engine module is at `Document_Decomposer/scripts/use/propose_angles.py`. Importing it is safe (`main()` guarded; stdlib top-level). It needs `scripts/use` on `sys.path`.
- `concept_index.json` lives at `Document_Decomposer/reports/connection/concept_index.json` (present for the existing library). It may be absent for the desktop app's own library → degrade to `{}`.

---

## File Structure (all under `desktop_app/`)

- `src/autoreview_app/engine_bridge.py` — MODIFY: add `ENGINE_USE` + `ensure_engine_use_on_path()`
- `src/autoreview_app/writing/ideation.py` — `propose_candidate_angles(edges, cidx)`, `load_angles(edges_path, concept_index_path)`
- `src/autoreview_app/config.py` — MODIFY: add `concept_index_path` field + nothing else
- `src/autoreview_app/api.py` — MODIFY: `GET /writing/angles`
- Tests: `tests/test_ideation.py`, `tests/test_api_angles.py`

Boundaries: `engine_bridge` owns the path; `writing/ideation` wraps the engine candidate builder + file loading; `api` wires. Offline.

---

### Task 1: Use-path bridge + ideation wrapper

**Files:**
- Modify: `desktop_app/src/autoreview_app/engine_bridge.py`
- Create: `desktop_app/src/autoreview_app/writing/ideation.py`
- Test: `desktop_app/tests/test_ideation.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_ideation.py`:

```python
import json
from pathlib import Path

from autoreview_app.writing.ideation import load_angles, propose_candidate_angles

EDGES = [
    {"a": "S1", "b": "S2", "relation": "contradicts", "shared": {"topic": ["uptake"]}, "rationale": "disagree on uptake"},
    {"a": "S1", "b": "S3", "relation": "complements", "shared": {}, "rationale": "builds on"},
]
CIDX = {
    "methane uptake": {
        "n_central": 2, "n_passing": 6, "central": ["S1", "S2"],
        "passing": [{"paper": "S3"}], "gap_score": 0.9, "specific": True,
    },
}


def test_candidates_from_graph():
    out = propose_candidate_angles(EDGES, CIDX)
    assert len(out["tension"]) == 1
    assert out["tension"][0]["a"] == "S1"
    assert out["tension"][0]["why"] == "disagree on uptake"
    assert [g["concept"] for g in out["gaps"]] == ["methane uptake"]
    assert [s["concept"] for s in out["synthesis"]] == ["methane uptake"]


def test_load_angles_reads_files(tmp_path: Path):
    edges_path = tmp_path / "edges.json"
    edges_path.write_text(json.dumps({"edges": EDGES}), encoding="utf-8")
    cidx_path = tmp_path / "concept_index.json"
    cidx_path.write_text(json.dumps(CIDX), encoding="utf-8")

    out = load_angles(edges_path, cidx_path)
    assert len(out["tension"]) == 1
    assert out["gaps"][0]["concept"] == "methane uptake"


def test_load_angles_missing_files_empty(tmp_path: Path):
    out = load_angles(tmp_path / "nope.json", tmp_path / "nada.json")
    assert out == {"tension": [], "gaps": [], "synthesis": []}
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_ideation.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.writing.ideation'`.

- [ ] **Step 3: Add the use-path bridge.** In `desktop_app/src/autoreview_app/engine_bridge.py`, after `ensure_engine_write_on_path`, add:

```python
ENGINE_USE = ENGINE_SRC.parent / "scripts" / "use"


def ensure_engine_use_on_path() -> None:
    """Put the engine's scripts/use dir on sys.path (lazy; only ideation needs it)."""
    if not ENGINE_USE.is_dir():
        raise RuntimeError(
            f"Engine use scripts not found at {ENGINE_USE}; expected Document_Decomposer/scripts/use"
        )
    if str(ENGINE_USE) not in sys.path:
        sys.path.insert(0, str(ENGINE_USE))
```

(Leave the rest unchanged.)

- [ ] **Step 4: Implement the ideation wrapper** — `desktop_app/src/autoreview_app/writing/ideation.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import engine_bridge

engine_bridge.ensure_engine_use_on_path()  # adds Document_Decomposer/scripts/use to sys.path

import propose_angles as _angles  # engine module (now importable)  # noqa: E402

_EMPTY: dict[str, list] = {"tension": [], "gaps": [], "synthesis": []}


def propose_candidate_angles(edges: list[dict[str, Any]], cidx: dict[str, Any]) -> dict[str, Any]:
    """Deterministic candidate writing angles from the relation graph + concept index."""
    return _angles.build_candidates(edges, cidx)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def load_angles(edges_path: Path, concept_index_path: Path) -> dict[str, Any]:
    """Load edges.json + concept_index.json and build candidate angles.

    Missing/malformed inputs degrade to an empty candidate set (no error) — the
    connection layer may not have run for the current library.
    """
    edges_doc = _read_json(edges_path)
    cidx = _read_json(concept_index_path)
    edges = (edges_doc.get("edges") if isinstance(edges_doc, dict) else None) or []
    if not isinstance(cidx, dict):
        cidx = {}
    if not edges and not cidx:
        return dict(_EMPTY)
    return propose_candidate_angles(edges, cidx)
```

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_ideation.py -v
```

Expected: PASS (3 passed). If importing `propose_angles` fails, STOP and report the exact traceback (do NOT modify the engine).

- [ ] **Step 6: Commit.**

```powershell
git checkout -b feat/desktop-app-m6c
git add desktop_app/src/autoreview_app/engine_bridge.py desktop_app/src/autoreview_app/writing/ideation.py desktop_app/tests/test_ideation.py
git commit -m "feat(desktop): candidate writing angles from the relation graph"
```

---

### Task 2: `GET /writing/angles` endpoint

**Files:**
- Modify: `desktop_app/src/autoreview_app/config.py`
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api_angles.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_api_angles.py`:

```python
import json
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig

EDGES = [{"a": "S1", "b": "S2", "relation": "contradicts", "shared": {}, "rationale": "disagree"}]
CIDX = {"uptake": {"n_central": 2, "n_passing": 6, "central": ["S1", "S2"], "passing": [], "gap_score": 0.5, "specific": True}}


def test_angles_endpoint(tmp_path: Path):
    edges_path = tmp_path / "edges.json"
    edges_path.write_text(json.dumps({"edges": EDGES}), encoding="utf-8")
    cidx_path = tmp_path / "concept_index.json"
    cidx_path.write_text(json.dumps(CIDX), encoding="utf-8")

    config = AppConfig(library_dir=tmp_path / "library", edges_path=edges_path, concept_index_path=cidx_path)
    resp = TestClient(create_app(config)).get("/writing/angles")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tension"]) == 1
    assert body["gaps"][0]["concept"] == "uptake"


def test_angles_endpoint_empty_when_unconfigured(tmp_path: Path):
    config = AppConfig(library_dir=tmp_path / "library")  # no edges/concept paths
    resp = TestClient(create_app(config)).get("/writing/angles")
    assert resp.json() == {"tension": [], "gaps": [], "synthesis": []}
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_angles.py -v
```

Expected: FAIL — `AppConfig` has no `concept_index_path` (TypeError).

- [ ] **Step 3: Add `concept_index_path` to `AppConfig`.** In `desktop_app/src/autoreview_app/config.py`, add a field next to `edges_path`:

```python
    concept_index_path: Path | None = None
```

(It is a dataclass field with a default, so add it after `edges_path: Path | None = None` in the field list. Leave `index_db`/`authors_db` properties and `from_env` unchanged.)

- [ ] **Step 4: Add the route.** In `desktop_app/src/autoreview_app/api.py`, add the import near the other local imports:

```python
from .writing.ideation import load_angles
```

Inside `create_app`, before `return app`, add:

```python
    @app.get("/writing/angles")
    def writing_angles() -> dict[str, Any]:
        if config.edges_path is None and config.concept_index_path is None:
            return {"tension": [], "gaps": [], "synthesis": []}
        edges_path = config.edges_path or (config.library_dir.parent / "edges.json")
        cidx_path = config.concept_index_path or (config.library_dir.parent / "concept_index.json")
        return load_angles(edges_path, cidx_path)
```

(Leave existing routes unchanged.)

- [ ] **Step 5: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_angles.py -v
```

Expected: PASS (2 passed). Then confirm no regression: `.venv\Scripts\python -m pytest tests/test_config.py tests/test_api_browse.py -v` → 8 passed.

- [ ] **Step 6: Run the FULL suite** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -q
```

Expected: all green. Report the summary line.

- [ ] **Step 7: Commit.**

```powershell
git add desktop_app/src/autoreview_app/config.py desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api_angles.py
git commit -m "feat(desktop): GET /writing/angles surfaces candidate angles"
```

---

## Done criteria for M6c

- `propose_candidate_angles(edges, cidx)` returns deterministic tension/gap/synthesis candidates via the engine's `build_candidates`.
- `load_angles(edges_path, concept_index_path)` reads the two JSON files (graceful empties), builds candidates.
- `GET /writing/angles` returns the candidates (empty when unconfigured/absent).
- Full suite green. Branch `feat/desktop-app-m6c`; not pushed.

## Out of scope for M6c (later)

- The AI ranking/phrasing step (the engine's `SYSTEM` prompt that turns raw candidates into a few sharp, phrased angles) — a follow-up with an injected client.
- The full interrogation loop (user refines an angle, feeds it to M6b's `run_writing_loop`).
- Generating `edges.json`/`concept_index.json` for the desktop app's own imported papers (running the connection layer) — separate.

---

## Self-review (planner)

- **Coverage vs design §5.6 (ideation) + roadmap M6c:** candidate angles from the relation graph (tension/gap/synthesis) surfaced deterministically and over HTTP; AI ranking + the refinement loop deferred. ✓
- **Placeholders:** none. The one risk (importing `propose_angles`) is flagged with STOP-and-report. ✓
- **Type/name consistency:** `ensure_engine_use_on_path()` mirrors `ensure_engine_write_on_path()`; `propose_candidate_angles(edges, cidx)` + `load_angles(edges_path, concept_index_path)` (Task 1) used by the endpoint (Task 2). `AppConfig.concept_index_path` additive (existing callers unaffected; `from_env` unchanged). `GET /writing/angles` distinct from `/writing/check` + `/writing/draft`. ✓
