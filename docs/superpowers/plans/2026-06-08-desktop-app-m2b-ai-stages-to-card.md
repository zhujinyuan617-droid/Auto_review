# Desktop App M2b — AI stages → Literature Card + import job Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a clean package (from M2a) into a validated `literature_card.json` by running the engine's `sections → reading → card` AI stages **in-process with an injectable AI client** (real DeepSeek in production, a fake returning canned dicts in tests), and expose the whole "PDF → card" flow as an async import job behind `POST /papers/import` + `GET /jobs/{id}`.

**Architecture:** The engine's AI stages all funnel through one seam — `client.chat_json(messages, hint) -> dict`, with HTTP only inside `chat_text`. So a desktop `ai/` package reuses the engine's importable builder functions (`docdecomp.reading_blocks`, `docdecomp.slim_card`, and the `ai_organize_sections` script helpers) and calls an **injected** client. Production builds the real `OpenAICompatibleClient` from `load_ai_config`; tests inject a fake whose `chat_json` returns canned, structurally-valid dicts seeded from a real M2a-built package. A small in-process `jobs` registry runs `build_package_from_pdf` (M2a) + the AI pipeline on a background thread with status/progress. The API exposes import + job-status endpoints.

**Tech Stack:** Python 3.12 (`desktop_app/.venv`), the engine `docdecomp` package + `scripts/ai_organize_sections.py`, FastAPI, pytest. No real network in tests.

**Git:** branch `feat/desktop-app-m2b`; commit per task; no push; user merges after review.

**Depends on:** M1 (app + jobs scaffolding patterns) and M2a (`engine_bridge.build_package_from_pdf`, `PyMuPDFExtractor`, clean package on disk).

---

## Verified engine facts (from source — do not re-derive)

- **AI client seam** (`docdecomp/ai_client.py`): `OpenAICompatibleClient(config: AIConfig)`; `chat_json(messages, response_schema_hint) -> dict` delegates to `chat_text` (the ONLY HTTP method). `load_ai_config(root, config_path=None) -> AIConfig` reads `config/ai.local.json` (absent file is OK → uses `{}`), env overrides `DOCDECOMP_AI_BASE_URL/API_KEY/MODEL/...`; raises `AIClientError` only if base_url/api_key/model are empty after merge. **Never print api keys.**
- **Stage 1 sections** — helpers live in the script `scripts/ai_organize_sections.py` (importable after adding `Document_Decomposer/scripts` to `sys.path`): `load_package(paper_dir) -> (content, metadata)`, `build_prompt(content, metadata, max_text_chars) -> messages`, `validate_ai_sections(result, paper_id, allowed_block_ids) -> list[str]`. Output: `ai_sections.json` with `{paper_id, sections:[{section_id, order, title, section_kind, page_start, page_end, block_ids, notes}], warnings, validation_warnings?}`.
- **Stage 2 reading** — `docdecomp.reading_blocks`: `build_prompt(content, ai_sections, max_text_chars=650)`, `repair_plan_coverage(plan, content, ai_sections) -> list[str]`, `validate_plan(plan, content, ai_sections) -> list[str]`, `build_reading_package(plan, content, ai_sections) -> dict`, `build_merge_report(package, content, warnings) -> dict`, `render_reading_md(package, paper_dir) -> str`, `load_json(path)`. AI returns a **plan**: `{paper_id, reading_blocks:[{section_id, reading_type, source_block_ids, join_reason, confidence}], warnings}`. Outputs: `reading_blocks.plan.json`, `reading_blocks.json` (= package), `merge_report.json`, `reading.md`.
- **Stage 3 card** — `docdecomp.slim_card`: `build_slim_prompt(reading, metadata, max_block_chars=900)`, `ensure_slim_defaults(card, reading, metadata) -> dict`, `validate_slim_card(card) -> {"status": "ok"|"needs_fix", ...}`, `SLIM_SCHEMA_HINT`. Output: `literature_card.json` (slim, `schema_version="0.2.0"`, keys `paper_id, paper, classification, summary, ai_warnings`). Valid = a classification list non-empty AND `summary.objective` non-blank AND `summary.main_findings` non-empty AND `paper.title` non-blank.

---

## File Structure (all under `desktop_app/`)

- `src/autoreview_app/engine_bridge.py` — MODIFY: also add `Document_Decomposer/scripts` to `sys.path` (for the sections helpers) and export `ENGINE_SCRIPTS`.
- `src/autoreview_app/ai/__init__.py` — new subpackage marker.
- `src/autoreview_app/ai/client.py` — `build_ai_client(config_root, config_path=None) -> OpenAICompatibleClient`.
- `src/autoreview_app/ai/stages.py` — `run_sections_stage`, `run_reading_stage`, `run_card_stage`, `run_ai_pipeline` (each takes `paper_dir` + an injected `client`).
- `src/autoreview_app/jobs.py` — tiny in-process job registry (submit a callable on a background thread; status/progress/result).
- `src/autoreview_app/importer.py` — `import_pdf(pdf_path, library_dir, docling_dir, extractor, client)` chaining M2a package build + `run_ai_pipeline`.
- `src/autoreview_app/api.py` — MODIFY: `POST /papers/import`, `GET /jobs/{id}`.
- Tests: `tests/_fake_ai.py`, `tests/test_ai_client.py`, `tests/test_ai_stages.py`, `tests/test_jobs.py`, `tests/test_importer.py`, plus api import tests in `tests/test_api_import.py`.

Boundaries: `ai/client` builds a client; `ai/stages` runs engine builders with an injected client; `jobs` is generic async; `importer` composes M2a+stages; `api` only wires HTTP. Each is testable with a fake client + a real M2a package (no network).

---

### Task 1: Engine scripts on path + AI client builder + fake-AI test util

**Files:**
- Modify: `desktop_app/src/autoreview_app/engine_bridge.py`
- Create: `desktop_app/src/autoreview_app/ai/__init__.py`
- Create: `desktop_app/src/autoreview_app/ai/client.py`
- Create: `desktop_app/tests/_fake_ai.py`
- Test: `desktop_app/tests/test_ai_client.py`

- [ ] **Step 1: Write the failing test** — `desktop_app/tests/test_ai_client.py`:

```python
from pathlib import Path

from autoreview_app.ai.client import build_ai_client


def test_build_ai_client_from_env(monkeypatch, tmp_path: Path):
    # No config file; supply the 3 mandatory values via env so no network/secret is needed.
    monkeypatch.setenv("DOCDECOMP_AI_BASE_URL", "http://fake.local")
    monkeypatch.setenv("DOCDECOMP_AI_API_KEY", "fake-key")
    monkeypatch.setenv("DOCDECOMP_AI_MODEL", "fake-model")

    client = build_ai_client(config_root=tmp_path)

    # It is the engine's real client class, configured but not yet talking to anything.
    assert client.config.base_url == "http://fake.local"
    assert client.config.model == "fake-model"
    assert hasattr(client, "chat_json")
```

- [ ] **Step 2: Run to verify it fails** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_ai_client.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.ai'`.

- [ ] **Step 3: Add a LAZY engine-scripts path helper.** In `desktop_app/src/autoreview_app/engine_bridge.py`, after the existing imports (`from .paper_ids import allocate_paper_id`), add a deferred helper (NOT executed at import — scripts are only needed by the AI stages, and engine_bridge itself only needs the engine src):

```python
# The engine's CLI scripts dir (Document_Decomposer/scripts) holds some helpers
# (e.g. ai_organize_sections) the AI stages import. Adding ~18 script modules to
# sys.path is a side effect only the stage code needs, so it is LAZY: callers
# invoke ensure_engine_scripts_on_path() right before importing a script module,
# rather than failing at engine_bridge import time when no consumer needs it.
ENGINE_SCRIPTS = ENGINE_SRC.parent / "scripts"


def ensure_engine_scripts_on_path() -> None:
    if not ENGINE_SCRIPTS.is_dir():
        raise RuntimeError(
            f"Engine scripts not found at {ENGINE_SCRIPTS}; expected Document_Decomposer/scripts"
        )
    if str(ENGINE_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(ENGINE_SCRIPTS))
```

(Leave the rest of `engine_bridge.py` unchanged.)

- [ ] **Step 4: Create the ai subpackage marker** — `desktop_app/src/autoreview_app/ai/__init__.py`:

```python
"""AI stages: run the engine's sections/reading/card stages with an injected client."""
```

- [ ] **Step 5: Implement the client builder** — `desktop_app/src/autoreview_app/ai/client.py`:

```python
from __future__ import annotations

from pathlib import Path

from .. import engine_bridge  # noqa: F401  # ensures engine src is on sys.path

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config


def build_ai_client(config_root: Path, config_path: Path | None = None) -> OpenAICompatibleClient:
    """Build the engine's real AI client from config (file or env). No network here."""
    config = load_ai_config(config_root, config_path)
    return OpenAICompatibleClient(config)
```

- [ ] **Step 6: Create the fake-AI test util** — `desktop_app/tests/_fake_ai.py`:

```python
from __future__ import annotations

from typing import Any


class SequencedFakeClient:
    """A stand-in AI client: chat_json returns the next canned dict, in order.

    The AI pipeline calls chat_json once per stage (sections, reading, card), so
    a list of three canned dicts drives a full offline run.
    """

    def __init__(self, responses: list[dict[str, Any]]):
        self._responses = list(responses)
        self._calls: list[tuple[list[dict], str]] = []

    def chat_json(self, messages: list[dict[str, str]], response_schema_hint: str) -> dict[str, Any]:
        self._calls.append((messages, response_schema_hint))
        if not self._responses:
            raise AssertionError("SequencedFakeClient ran out of canned responses")
        return self._responses.pop(0)

    @property
    def call_count(self) -> int:
        return len(self._calls)
```

- [ ] **Step 7: Run the test to verify it passes** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_ai_client.py -v
```

Expected: PASS (1 passed). If it fails importing `docdecomp.ai_client`, STOP and report.

- [ ] **Step 8: Commit.**

```powershell
git add desktop_app/src/autoreview_app/engine_bridge.py desktop_app/src/autoreview_app/ai/__init__.py desktop_app/src/autoreview_app/ai/client.py desktop_app/tests/_fake_ai.py desktop_app/tests/test_ai_client.py
git commit -m "feat(desktop): AI client builder + engine scripts on path + fake client"
```

---

### Task 2: AI stage wrappers (sections → reading → card)

**Files:**
- Create: `desktop_app/src/autoreview_app/ai/stages.py`
- Test: `desktop_app/tests/test_ai_stages.py`

This task runs the three engine stages in-process with an injected client, seeded by a REAL M2a clean package, and asserts the output files are produced with the right shape. The canned AI dicts are built from the real `content_blocks.json` block ids so the engine builders accept them.

- [ ] **Step 1: Write the failing test** — `desktop_app/tests/test_ai_stages.py`:

```python
import json
from pathlib import Path

from _fake_ai import SequencedFakeClient
from _pdf_helpers import make_pdf

from autoreview_app.engine_bridge import build_package_from_pdf
from autoreview_app.extract.pymupdf_extractor import PyMuPDFExtractor
from autoreview_app.ai.stages import run_ai_pipeline


def _seed_package(tmp_path: Path) -> Path:
    pdf = make_pdf(tmp_path / "p.pdf", ["Intro: the problem is X.", "Methods: we did Y. Result: Z."])
    library = tmp_path / "library"
    build_package_from_pdf(
        pdf_path=pdf, library_dir=library, docling_json_dir=tmp_path / "dj",
        extractor=PyMuPDFExtractor(),
    )
    return library / "S1"


def _canned(paper_dir: Path):
    content = json.loads((paper_dir / "content_blocks.json").read_text(encoding="utf-8"))
    block_ids = [b["block_id"] for b in content["blocks"]]
    paper_id = content["paper_id"]
    sections = {
        "paper_id": paper_id,
        "sections": [{
            "section_id": f"{paper_id}-AISEC-001", "order": 1, "title": "Body",
            "section_kind": "introduction", "page_start": 1, "page_end": 2,
            "block_ids": block_ids, "notes": "",
        }],
        "warnings": [],
    }
    reading = {
        "paper_id": paper_id,
        "reading_blocks": [{
            "section_id": f"{paper_id}-AISEC-001", "reading_type": "paragraph",
            "source_block_ids": block_ids, "join_reason": "same paragraph", "confidence": 0.9,
        }],
        "warnings": [],
    }
    card = {
        "paper": {"title": "A Study of Z", "doi": "", "year": "2020", "journal": "", "paper_type": "article"},
        "classification": {"research_objects": ["X"], "methods": ["Y"], "domain_tags": ["z"], "gas_systems": [], "scale": []},
        "summary": {"objective": "Investigate X.", "main_findings": ["Z happens."], "methods_systems": "Y"},
        "ai_warnings": [],
    }
    return [sections, reading, card]


def test_run_ai_pipeline_produces_card(tmp_path: Path):
    paper_dir = _seed_package(tmp_path)
    client = SequencedFakeClient(_canned(paper_dir))

    run_ai_pipeline(paper_dir, client)

    assert client.call_count == 3  # sections, reading, card
    assert (paper_dir / "ai_sections.json").exists()
    assert (paper_dir / "reading_blocks.json").exists()

    card = json.loads((paper_dir / "literature_card.json").read_text(encoding="utf-8"))
    assert card["schema_version"] == "0.2.0"
    assert card["paper"]["title"] == "A Study of Z"
    assert card["summary"]["main_findings"] == ["Z happens."]
```

- [ ] **Step 2: Run to verify it fails** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_ai_stages.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.ai.stages'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/ai/stages.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .. import engine_bridge

engine_bridge.ensure_engine_scripts_on_path()  # adds Document_Decomposer/scripts to sys.path

import ai_organize_sections as sections_stage  # engine script (now importable)  # noqa: E402
from docdecomp.io_utils import atomic_write_text, write_json
from docdecomp.reading_blocks import (
    build_merge_report,
    build_prompt as build_reading_prompt,
    build_reading_package,
    load_json,
    render_reading_md,
    repair_plan_coverage,
    validate_plan,
)
from docdecomp.slim_card import (
    SLIM_SCHEMA_HINT,
    build_slim_prompt,
    ensure_slim_defaults,
    validate_slim_card,
)

SECTIONS_HINT = "Return JSON with paper_id, sections[], warnings[]."
READING_HINT = "Return JSON with paper_id, reading_blocks[], warnings[]."


class AIClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]], response_schema_hint: str) -> dict[str, Any]:
        ...


def run_sections_stage(paper_dir: Path, client: AIClient) -> dict[str, Any]:
    content, metadata = sections_stage.load_package(paper_dir)
    messages = sections_stage.build_prompt(content, metadata, 900)
    result = client.chat_json(messages, SECTIONS_HINT)
    allowed = {b["block_id"] for b in content.get("blocks", [])}
    warnings = sections_stage.validate_ai_sections(result, content.get("paper_id", ""), allowed)
    if warnings:
        result["validation_warnings"] = warnings
    write_json(paper_dir / "ai_sections.json", result)
    return result


def run_reading_stage(paper_dir: Path, client: AIClient) -> dict[str, Any]:
    content = load_json(paper_dir / "content_blocks.json")
    ai_sections = load_json(paper_dir / "ai_sections.json")
    messages = build_reading_prompt(content, ai_sections, 650)
    plan = client.chat_json(messages, READING_HINT)
    warnings = [*repair_plan_coverage(plan, content, ai_sections), *validate_plan(plan, content, ai_sections)]
    package = build_reading_package(plan, content, ai_sections)
    report = build_merge_report(package, content, warnings)
    write_json(paper_dir / "reading_blocks.plan.json", plan)
    write_json(paper_dir / "reading_blocks.json", package)
    write_json(paper_dir / "merge_report.json", report)
    atomic_write_text(paper_dir / "reading.md", render_reading_md(package, paper_dir), encoding="utf-8")
    return package


def run_card_stage(paper_dir: Path, client: AIClient) -> dict[str, Any]:
    reading = load_json(paper_dir / "reading_blocks.json")
    metadata = load_json(paper_dir / "metadata_candidates.json")
    messages = build_slim_prompt(reading, metadata, 900)
    raw = client.chat_json(messages, SLIM_SCHEMA_HINT)
    card = ensure_slim_defaults(raw, reading, metadata)
    card["validation"] = validate_slim_card(card)
    write_json(paper_dir / "literature_card.json", card)
    return card


def run_ai_pipeline(paper_dir: Path, client: AIClient) -> dict[str, Any]:
    run_sections_stage(paper_dir, client)
    run_reading_stage(paper_dir, client)
    return run_card_stage(paper_dir, client)
```

- [ ] **Step 4: Run to verify it passes** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_ai_stages.py -v
```

Expected: PASS (1 passed). If an engine builder rejects the canned data (e.g. `build_reading_package` raises on the plan shape, or `validate_slim_card` mutates structure unexpectedly), STOP and report the exact engine error + the canned dict used — do NOT loosen the assertions to force a pass; report so the canned shape can be corrected against the real engine.

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/ai/stages.py desktop_app/tests/test_ai_stages.py
git commit -m "feat(desktop): run sections/reading/card stages with injected AI client"
```

---

### Task 3: In-process job runner

**Files:**
- Create: `desktop_app/src/autoreview_app/jobs.py`
- Test: `desktop_app/tests/test_jobs.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_jobs.py`:

```python
import time

from autoreview_app.jobs import JobRegistry


def _wait(reg, job_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = reg.get(job_id)["status"]
        if status in {"succeeded", "failed"}:
            return reg.get(job_id)
        time.sleep(0.02)
    raise AssertionError("job did not finish in time")


def test_successful_job_reports_result():
    reg = JobRegistry()
    job_id = reg.submit(lambda report: report("hi") or 42)
    final = _wait(reg, job_id)
    assert final["status"] == "succeeded"
    assert final["result"] == 42
    assert "hi" in final["progress"]


def test_failed_job_reports_error():
    reg = JobRegistry()

    def boom(report):
        raise ValueError("nope")

    job_id = reg.submit(boom)
    final = _wait(reg, job_id)
    assert final["status"] == "failed"
    assert "nope" in final["error"]


def test_unknown_job_is_none():
    assert JobRegistry().get("missing") is None
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_jobs.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.jobs'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/jobs.py`:

```python
from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

# A job is a callable taking one arg: report(msg) to append a progress line.
Job = Callable[[Callable[[str], None]], Any]


class JobRegistry:
    """Runs jobs on background threads and tracks status/progress/result/error."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, job: Job) -> str:
        job_id = uuid.uuid4().hex
        with self._lock:
            self._jobs[job_id] = {"status": "running", "progress": [], "result": None, "error": None}
        thread = threading.Thread(target=self._run, args=(job_id, job), daemon=True)
        thread.start()
        return job_id

    def _run(self, job_id: str, job: Job) -> None:
        def report(message: str) -> None:
            with self._lock:
                self._jobs[job_id]["progress"].append(message)

        try:
            result = job(report)
            with self._lock:
                self._jobs[job_id]["result"] = result
                self._jobs[job_id]["status"] = "succeeded"
        except Exception as exc:  # noqa: BLE001 — surfaced to the caller via status
            with self._lock:
                self._jobs[job_id]["error"] = f"{type(exc).__name__}: {exc}"
                self._jobs[job_id]["status"] = "failed"

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job is not None else None
```

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_jobs.py -v
```

Expected: PASS (3 passed).

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/jobs.py desktop_app/tests/test_jobs.py
git commit -m "feat(desktop): in-process background job registry"
```

---

### Task 4: `import_pdf` — compose M2a package build + AI pipeline

**Files:**
- Create: `desktop_app/src/autoreview_app/importer.py`
- Test: `desktop_app/tests/test_importer.py`

- [ ] **Step 1: Write the failing test** — `desktop_app/tests/test_importer.py`:

```python
import json
from pathlib import Path

from _fake_ai import SequencedFakeClient
from _pdf_helpers import make_pdf

from autoreview_app.extract.pymupdf_extractor import PyMuPDFExtractor
from autoreview_app.importer import import_pdf
from test_ai_stages import _canned  # reuse the canned-builder


def test_import_pdf_returns_paper_id_and_writes_card(tmp_path: Path):
    pdf = make_pdf(tmp_path / "doc.pdf", ["Intro problem.", "Methods and result Z."])
    library = tmp_path / "library"
    docling_dir = tmp_path / "dj"

    # We must build canned responses from the package, but import_pdf builds the package
    # internally. So pre-build with a throwaway dir to learn block ids, then run for real.
    # Simpler: import_pdf accepts a client factory that is given the paper_dir.
    def client_factory(paper_dir: Path):
        return SequencedFakeClient(_canned(paper_dir))

    paper_id = import_pdf(
        pdf_path=pdf, library_dir=library, docling_json_dir=docling_dir,
        extractor=PyMuPDFExtractor(), client_factory=client_factory,
        progress=lambda msg: None,
    )

    assert paper_id == "S1"
    card = json.loads((library / "S1" / "literature_card.json").read_text(encoding="utf-8"))
    assert card["schema_version"] == "0.2.0"
    assert card["paper"]["title"]
```

- [ ] **Step 2: Run to verify it fails** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_importer.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.importer'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/importer.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Protocol

from .ai.stages import run_ai_pipeline
from .engine_bridge import build_package_from_pdf


class _Extractor(Protocol):
    name: str

    def extract(self, pdf_path: Path) -> dict[str, Any]:
        ...


def import_pdf(
    pdf_path: Path,
    library_dir: Path,
    docling_json_dir: Path,
    extractor: _Extractor,
    client_factory: Callable[[Path], Any],
    progress: Callable[[str], None],
) -> str:
    """PDF -> clean package (M2a) -> AI card (M2b). Returns the paper id.

    client_factory is given the paper dir and returns an AI client; this lets the
    real app build one client from config while tests inject a fake seeded from the
    just-built package.
    """
    progress("extracting pdf")
    paper_id = build_package_from_pdf(pdf_path, library_dir, docling_json_dir, extractor)
    paper_dir = library_dir / paper_id
    progress("running ai stages")
    client = client_factory(paper_dir)
    run_ai_pipeline(paper_dir, client)
    progress("done")
    return paper_id
```

Note: reuse the existing `PdfExtractor` protocol instead of a local one if cleaner — but a local Protocol here is acceptable to avoid a hard import cycle; the reviewer may consolidate.

- [ ] **Step 4: Run to verify it passes** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_importer.py -v
```

Expected: PASS (1 passed).

- [ ] **Step 5: Commit.**

```powershell
git add desktop_app/src/autoreview_app/importer.py desktop_app/tests/test_importer.py
git commit -m "feat(desktop): import_pdf composes package build + AI card"
```

---

### Task 5: `POST /papers/import` + `GET /jobs/{id}`

**Files:**
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api_import.py`

The endpoint must be testable without a real AI client. `create_app` gains an optional `import_runner` callable (defaulting to the real one); tests inject a fake runner that just records the call and returns a paper id, so the HTTP layer is tested in isolation from the AI pipeline (which Task 4 already covers).

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_api_import.py`:

```python
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(tmp_path: Path, import_runner):
    app = create_app(AppConfig(library_dir=tmp_path / "library"), import_runner=import_runner)
    return TestClient(app)


def test_import_starts_a_job_and_reports_success(tmp_path: Path):
    def fake_runner(pdf_path, progress):
        progress("working")
        return "S1"

    client = _client(tmp_path, fake_runner)
    resp = client.post("/papers/import", json={"pdf_path": str(tmp_path / "x.pdf")})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    # Poll the job to completion.
    import time
    for _ in range(200):
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert status["status"] == "succeeded"
    assert status["result"] == "S1"


def test_unknown_job_404(tmp_path: Path):
    client = _client(tmp_path, lambda pdf_path, progress: "S1")
    assert client.get("/jobs/nope").status_code == 404
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_import.py -v
```

Expected: FAIL — `create_app()` does not accept `import_runner` yet (TypeError).

- [ ] **Step 3: Implement.** Edit `desktop_app/src/autoreview_app/api.py`. Change the top of the file to add imports and a default runner, and extend `create_app`. Replace the whole file with:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import AppConfig
from .jobs import JobRegistry
from .library_index import list_papers

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"

# An import runner takes (pdf_path, progress_callback) and returns the new paper id.
ImportRunner = Callable[[Path, Callable[[str], None]], str]


class ImportRequest(BaseModel):
    pdf_path: str


def create_app(config: AppConfig, import_runner: ImportRunner | None = None) -> FastAPI:
    app = FastAPI(title="Auto Review Desktop", version="0.1.0")
    jobs = JobRegistry()
    runner = import_runner if import_runner is not None else _default_import_runner(config)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/library")
    def library() -> dict:
        return {"papers": list_papers(config.library_dir)}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.post("/papers/import")
    def import_paper(req: ImportRequest) -> dict:
        pdf_path = Path(req.pdf_path)
        job_id = jobs.submit(lambda report: runner(pdf_path, report))
        return {"job_id": job_id}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str) -> dict[str, Any]:
        status = jobs.get(job_id)
        if status is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return status

    return app


def _default_import_runner(config: AppConfig) -> ImportRunner:
    """Wire the real importer lazily so tests that inject a runner never import it."""

    def run(pdf_path: Path, progress: Callable[[str], None]) -> str:
        from .ai.client import build_ai_client
        from .extract.pymupdf_extractor import PyMuPDFExtractor
        from .importer import import_pdf

        engine_root = Path(__file__).resolve().parents[3] / "Document_Decomposer"
        docling_dir = config.library_dir.parent / "docling_json"
        return import_pdf(
            pdf_path=pdf_path,
            library_dir=config.library_dir,
            docling_json_dir=docling_dir,
            extractor=PyMuPDFExtractor(),
            client_factory=lambda paper_dir: build_ai_client(engine_root),
            progress=progress,
        )

    return run
```

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_import.py -v
```

Expected: PASS (2 passed). Then re-run the existing api tests to confirm no regression: `.venv\Scripts\python -m pytest tests/test_api.py -v` → 4 passed.

- [ ] **Step 5: Run the FULL suite** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -q
```

Expected: all green (M1 + M2a + M2b). Report the summary line. A httpx/starlette deprecation warning is acceptable.

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api_import.py
git commit -m "feat(desktop): POST /papers/import + GET /jobs/{id} via job registry"
```

---

## Done criteria for M2b

- `sections → reading → card` run in-process with an injected client; a real M2a-seeded package yields a `literature_card.json` (schema 0.2.0) with the canned title/findings — proving the engine builders are driven correctly offline.
- A background job registry runs work off-thread with status/progress/result/error.
- `POST /papers/import` starts an import job; `GET /jobs/{id}` reports status (404 for unknown).
- Full suite green. Branch `feat/desktop-app-m2b`; not pushed.

## Out of scope for M2b (later)

- A real-DeepSeek end-to-end smoke (needs the user's `config/ai.local.json`); run manually, not in the auto suite. Document the command in the desktop README during M7 polish.
- The engine's AI cache + card retry/repair loop (M2b runs stages fresh, single card attempt) — add later if cost/quality needs it.
- UI for import progress (M4+).
- Docling as a second extractor (later).

---

## Self-review (planner)

- **Coverage vs roadmap M2 second half:** AI stages wrapped with injected client (Task 2), job runner (Task 3), import endpoint (Task 5), composed importer (Task 4), client builder (Task 1). The real-AI smoke is explicitly deferred. ✓
- **Placeholders:** none — full code/commands per step. The two risk points (canned AI dicts must satisfy engine builders; engine script import for sections) are flagged with explicit "STOP and report" instructions rather than hidden. ✓
- **Type/name consistency:** `run_ai_pipeline(paper_dir, client)` defined Task 2, used Task 4. `import_pdf(..., client_factory, progress)` defined Task 4, the api `_default_import_runner` matches that signature. `JobRegistry.submit(job)/get(id)` defined Task 3, used Task 5. `create_app(config, import_runner=None)` extended in Task 5 matches the M1 single-arg callers (default keeps them working). `build_ai_client(config_root, config_path=None)` Task 1, used Task 5. ✓
