# Desktop App M6b — Writing loop (author → gates → experts → adjudicator)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Drive the engine's writing loop in-process with injected AI clients: one round = author draft → mechanical gates (+ deterministic citation repair) → 4 expert reviews → adjudicator/acceptance gate; loop until internal acceptance or max rounds. Expose it as a background draft job (`POST /writing/draft`). Fully offline-testable with fake clients.

**Architecture:** The engine's `run_writing_loop.py` keeps the per-round orchestration inside a monolithic `main()`, but every stage is a separate importable function taking an explicit `client`: `call_json` (author), `mechanical_gates`, `is_citation_only_failure`, `repair_citations`, `review_experts`, `build_revision_plan`, `decide_gate`, `mechanical_revision_plan`. So the desktop `writing/loop.py` **replicates the main-loop body** by calling those engine functions (it reuses the engine's prompts at `PROMPTS` and rubric at `RUBRIC_PATH` internally) with injected clients and a temp run dir. Production injects real `OpenAICompatibleClient`s built from config; tests inject fakes returning canned drafts/reviews. The brief is provided to the loop (building a real brief from cards+edges is deferred). The endpoint runs the loop as a `JobRegistry` job, with an injectable runner for tests.

**Tech Stack:** Python 3.12 (`desktop_app/.venv`), the engine `run_writing_loop` module, FastAPI, pytest. No new deps.

**Git:** branch `feat/desktop-app-m6b`; commit per task; no push; user merges after review.

**Depends on:** M2b (`engine_bridge`, `JobRegistry`, `SequencedFakeClient`), M6a (`ensure_engine_write_on_path`). Run from `desktop_app/` with `.venv\Scripts\python`.

---

## Verified facts (from `run_writing_loop.py` — do not re-derive)

- `call_json(client, system_prompt, payload, schema_hint, input_path=None) -> dict` — builds messages, calls `client.chat_json`. The author call uses prompt `PROMPTS/"author_deepseek.md"`, payload `{"brief", "previous_reviews_and_revision_plans", "round"}`, schema hint `'Respond with JSON: {"draft_markdown":"","claim_register":[],"self_check":{}}'`. Returns a `draft_obj` with keys `draft_markdown`, `claim_register`, `self_check`.
- `write_author_round(run_dir, round_index, draft_obj) -> Path` — writes `draft_vNN.md` + claim_register + self_check; returns the draft path.
- `mechanical_gates(brief, draft_text, draft_obj) -> dict` — `{evidence, citation, style, completeness, passed}`. `passed = evidence.passed AND citation.passed AND completeness.passed`.
  - `evidence_gate`: `numeric_tokens` strips `S\d+` BEFORE extracting numbers, so `[S09]` leaks no number. A clean draft with no other numbers + claim_register entries each having non-empty `support_text` and `claim_ids` that normalize into `brief["claim_catalog"]` ids passes. (`normalize_claim_id("C1") == "C0001"`.)
  - `completeness_gate`: only enforced when `brief["manuscript_mode"] in {"full","fusion"}`; otherwise passes.
- `is_citation_only_failure(gate_result)` — True iff evidence passed AND there's a citation failure. Then `repair_citations(client, run_dir, round_label, brief, draft_obj, gate_result) -> (obj, path, gate)` (deterministic, ignores client).
- `review_experts(client, run_dir, round_index, brief, draft, draft_obj, mechanical_gate_result) -> list[dict]` — 4 sequential `client.chat_json` calls (experts structure/evidence/science/language), reads `RUBRIC_PATH` + expert prompts (present on disk). Each review gets `expert_id`.
- `decide_gate(reviews) -> "internal_acceptance_gate" | "continue"` — acceptance iff all decisions in `{minor_revision, accept}` AND no review has `fatal_issues`/`major_issues`.
- `build_revision_plan(client, run_dir, round_index, reviews) -> dict` — if acceptance, returns a record WITHOUT calling the client; else 1 adjudicator `client.chat_json`.
- `mechanical_revision_plan(gate_result) -> dict` — pure (no client) revision plan when mechanical gates fail.
- The engine main loop, per round: author → write → gates → (citation-only? repair) → if not passed: mechanical_revision_plan (experts skipped) else: review_experts + build_revision_plan + set `decision["gate_decision"] = decide_gate(reviews)`; break when `gate_decision == "internal_acceptance_gate"`.

---

## File Structure (all under `desktop_app/`)

- `src/autoreview_app/writing/loop.py` — `run_writing_round(...)`, `run_writing_loop(...)`
- `src/autoreview_app/api.py` — MODIFY: `POST /writing/draft`
- Tests: `tests/test_writing_loop.py`, `tests/test_api_writing_draft.py`

Boundaries: `writing/loop` replicates the engine round/loop using engine functions; `api` wires a job. Offline-testable with fake clients / fake runner.

---

### Task 1: `run_writing_round` + `run_writing_loop`

**Files:**
- Create: `desktop_app/src/autoreview_app/writing/loop.py`
- Test: `desktop_app/tests/test_writing_loop.py`

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_writing_loop.py`:

```python
from pathlib import Path

from _fake_ai import SequencedFakeClient

from autoreview_app.writing.loop import run_writing_loop, run_writing_round

# A brief whose claim_catalog admits claim id C1 (normalizes to C0001).
BRIEF = {"claim_catalog": [{"claim_id": "C1"}], "topic": "methane"}

# A clean author draft that passes all mechanical gates (no stray numbers;
# claim_register entry has support_text + a valid claim_id).
CLEAN_DRAFT = {
    "draft_markdown": "Adsorption increases with pressure [S09].",
    "claim_register": [{"claim": "adsorption rises", "support_text": "the study shows", "claim_ids": ["C1"]}],
    "self_check": {},
}

# An expert review that accepts with no blocking issues.
def _accept_review():
    return {"decision": "accept", "scores": {"overall": 5}, "fatal_issues": [], "major_issues": [],
            "minor_issues": [], "strengths": ["clear"], "summary": "ok"}


def test_round_reaches_acceptance(tmp_path: Path):
    author = SequencedFakeClient([CLEAN_DRAFT])
    experts = SequencedFakeClient([_accept_review() for _ in range(4)])

    result = run_writing_round(
        brief=BRIEF, run_dir=tmp_path, round_index=1, revision_history=[],
        author_client=author, expert_client=experts,
    )

    assert author.call_count == 1          # author called once
    assert experts.call_count == 4         # 4 expert reviews
    assert result["decision"]["gate_decision"] == "internal_acceptance_gate"
    assert Path(result["draft_path"]).exists()


def test_round_mechanical_failure_skips_experts(tmp_path: Path):
    # Draft with a leaked number (42 not in brief) + no claims -> evidence gate fails.
    bad_draft = {"draft_markdown": "Adsorption is 42 units high [S09].", "claim_register": [], "self_check": {}}
    author = SequencedFakeClient([bad_draft])
    experts = SequencedFakeClient([])  # must not be called

    result = run_writing_round(
        brief=BRIEF, run_dir=tmp_path, round_index=1, revision_history=[],
        author_client=author, expert_client=experts,
    )

    assert experts.call_count == 0
    assert result["decision"]["gate_decision"] != "internal_acceptance_gate"


def test_loop_stops_at_acceptance(tmp_path: Path):
    author = SequencedFakeClient([CLEAN_DRAFT, CLEAN_DRAFT, CLEAN_DRAFT])
    experts = SequencedFakeClient([_accept_review() for _ in range(12)])

    summary = run_writing_loop(
        brief=BRIEF, run_dir=tmp_path, max_rounds=3,
        author_client=author, expert_client=experts,
    )

    assert summary["status"] == "internal_acceptance_gate"
    assert summary["rounds"] == 1  # stops after the first accepting round
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_writing_loop.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'autoreview_app.writing.loop'`.

- [ ] **Step 3: Implement** — `desktop_app/src/autoreview_app/writing/loop.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .. import engine_bridge

engine_bridge.ensure_engine_write_on_path()  # adds Document_Decomposer/scripts/write to sys.path

import run_writing_loop as _wl  # engine module (now importable)  # noqa: E402

_AUTHOR_HINT = 'Respond with JSON: {"draft_markdown":"","claim_register":[],"self_check":{}}'


class AIClient(Protocol):
    def chat_json(self, messages: list[dict[str, str]], response_schema_hint: str) -> dict[str, Any]:
        ...


def run_writing_round(
    brief: dict[str, Any],
    run_dir: Path,
    round_index: int,
    revision_history: list[dict[str, Any]],
    author_client: AIClient,
    expert_client: AIClient,
) -> dict[str, Any]:
    """One writing round, replicating the engine main-loop body with injected clients.

    author draft -> mechanical gates -> (citation-only? deterministic repair) ->
    if gates fail: mechanical revision plan (experts skipped); else 4 expert reviews
    + adjudicator/acceptance gate. Returns {decision, draft_path, reviews}.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    round_label = f"v{round_index:02d}"
    payload = {"brief": brief, "previous_reviews_and_revision_plans": revision_history, "round": round_index}

    draft_obj = _wl.call_json(
        author_client, _wl.read_text(_wl.PROMPTS / "author_deepseek.md"),
        payload, _AUTHOR_HINT, run_dir / f"input_author_{round_label}.json",
    )
    draft_path = _wl.write_author_round(run_dir, round_index, draft_obj)
    draft_text = _wl.read_text(draft_path)
    gate_result = _wl.mechanical_gates(brief, draft_text, draft_obj)
    _wl.write_json(run_dir / f"mechanical_gates_{round_label}.json", gate_result)

    active_obj, active_path, active_gate = draft_obj, draft_path, gate_result
    if _wl.is_citation_only_failure(gate_result):
        active_obj, active_path, active_gate = _wl.repair_citations(
            author_client, run_dir, round_label, brief, draft_obj, gate_result,
        )

    if not active_gate.get("passed"):
        reviews: list[dict[str, Any]] = []
        decision = _wl.mechanical_revision_plan(active_gate)
        decision.setdefault("gate_decision", "continue")
    else:
        reviews = _wl.review_experts(
            expert_client, run_dir, round_index, brief,
            _wl.read_text(active_path), active_obj, active_gate,
        )
        decision = _wl.build_revision_plan(expert_client, run_dir, round_index, reviews)
        decision["gate_decision"] = _wl.decide_gate(reviews)

    _wl.write_json(run_dir / f"decision_{round_label}.json", decision)
    return {"decision": decision, "draft_path": str(active_path), "reviews": reviews}


def run_writing_loop(
    brief: dict[str, Any],
    run_dir: Path,
    max_rounds: int,
    author_client: AIClient,
    expert_client: AIClient,
) -> dict[str, Any]:
    """Run rounds until internal acceptance or max_rounds. Returns a summary."""
    history: list[dict[str, Any]] = []
    status = "continue"
    for round_index in range(1, max_rounds + 1):
        result = run_writing_round(
            brief, run_dir, round_index, history, author_client, expert_client,
        )
        history.append({"round": round_index, **result})
        if result["decision"].get("gate_decision") == "internal_acceptance_gate":
            status = "internal_acceptance_gate"
            break
    return {"status": status, "rounds": len(history), "history": history}
```

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_writing_loop.py -v
```

Expected: PASS (3 passed). If a mechanical gate rejects the CLEAN_DRAFT (e.g. evidence gate flags something), STOP and report the exact `mechanical_gates` output + the canned draft — do NOT loosen the test or change the engine; report so the canned draft can be corrected against the real gates.

- [ ] **Step 5: Commit.**

```powershell
git checkout -b feat/desktop-app-m6b
git add desktop_app/src/autoreview_app/writing/loop.py desktop_app/tests/test_writing_loop.py
git commit -m "feat(desktop): writing round + loop driven by injected AI clients"
```

---

### Task 2: `POST /writing/draft` background job

**Files:**
- Modify: `desktop_app/src/autoreview_app/api.py`
- Test: `desktop_app/tests/test_api_writing_draft.py`

`create_app` gains an optional `draft_runner` (so the route is testable without AI). The route submits the runner as a `JobRegistry` job and returns a `job_id`; `GET /jobs/{id}` (from M2b) reports status/result.

- [ ] **Step 1: Write the failing tests** — `desktop_app/tests/test_api_writing_draft.py`:

```python
import time
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig


def _client(tmp_path: Path, draft_runner):
    app = create_app(AppConfig(library_dir=tmp_path / "library"), draft_runner=draft_runner)
    return TestClient(app)


def test_draft_runs_as_job(tmp_path: Path):
    def fake_runner(brief, progress):
        progress("writing")
        return {"status": "internal_acceptance_gate", "rounds": 1}

    client = _client(tmp_path, fake_runner)
    resp = client.post("/writing/draft", json={"brief": {"topic": "methane"}})
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    status = None
    for _ in range(200):
        status = client.get(f"/jobs/{job_id}").json()
        if status["status"] in {"succeeded", "failed"}:
            break
        time.sleep(0.02)
    assert status is not None and status["status"] == "succeeded", status
    assert status["result"]["status"] == "internal_acceptance_gate"


def test_draft_runner_not_configured_503(tmp_path: Path):
    app = create_app(AppConfig(library_dir=tmp_path / "library"))  # no draft_runner
    client = TestClient(app)
    assert client.post("/writing/draft", json={"brief": {}}).status_code == 503
```

- [ ] **Step 2: Run to verify they fail** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_writing_draft.py -v
```

Expected: FAIL — `create_app()` has no `draft_runner` kwarg (TypeError).

- [ ] **Step 3: Implement.** In `desktop_app/src/autoreview_app/api.py`:

(a) Add a type alias near `ImportRunner`/`SearchRunner`:

```python
# A draft runner takes (brief, progress) and returns a writing-loop summary dict.
DraftRunner = Callable[[dict[str, Any], Callable[[str], None]], dict[str, Any]]
```

(b) Add a request model near the others:

```python
class DraftRequest(BaseModel):
    brief: dict[str, Any]
```

(c) Change the `create_app` signature to add `draft_runner`:

```python
def create_app(
    config: AppConfig,
    import_runner: ImportRunner | None = None,
    search_runner: SearchRunner | None = None,
    draft_runner: DraftRunner | None = None,
) -> FastAPI:
```

(d) Inside `create_app`, before `return app`, add:

```python
    @app.post("/writing/draft")
    def writing_draft(req: DraftRequest) -> dict:
        if draft_runner is None:
            raise HTTPException(status_code=503, detail="draft runner not configured")
        job_id = jobs.submit(lambda report: draft_runner(req.brief, report))
        return {"job_id": job_id}
```

(`jobs` is the `JobRegistry` already created in `create_app` for `/papers/import`. Leave existing routes unchanged.)

- [ ] **Step 4: Run to verify they pass** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest tests/test_api_writing_draft.py -v
```

Expected: PASS (2 passed). Then confirm no regression: `.venv\Scripts\python -m pytest tests/test_api_import.py tests/test_api.py -v` → 6 passed.

- [ ] **Step 5: Run the FULL suite** (from `desktop_app/`):

```powershell
.venv\Scripts\python -m pytest -q
```

Expected: all green. Report the summary line.

- [ ] **Step 6: Commit.**

```powershell
git add desktop_app/src/autoreview_app/api.py desktop_app/tests/test_api_writing_draft.py
git commit -m "feat(desktop): POST /writing/draft runs the writing loop as a job"
```

---

## Done criteria for M6b

- `run_writing_round` replicates one engine round (author → gates → repair → experts/mechanical-plan → decision) with injected clients; reaches `internal_acceptance_gate` on clean canned input; skips experts on mechanical failure.
- `run_writing_loop` loops to acceptance or max rounds.
- `POST /writing/draft` runs the loop as a background job (503 if no runner); `GET /jobs/{id}` reports status/result.
- Full suite green. Branch `feat/desktop-app-m6b`; not pushed.

## Out of scope for M6b (next: M6c, and real wiring)

- **Real brief construction** from cards + edges + concept index (`build_writing_brief.build_brief` is importable but takes an argparse.Namespace and otherwise runs as a subprocess) — wire a `_default_draft_runner` that builds the brief and injects real clients, mirroring `_default_import_runner`. M6b ships the loop engine + endpoint with the brief provided.
- **M6c — ideation/interrogation** (`propose_angles` → user refines → feed angle into the loop).
- A real-DeepSeek end-to-end writing smoke (manual; needs config + brief inputs).

---

## Self-review (planner)

- **Coverage vs design §5.6 (writing core) + roadmap M6:** the interrogation→draft→expert loop's draft+gate+expert+adjudicate spine is delivered (round + loop), exposed as a job. Real brief-building and ideation are deferred (M6c + wiring). ✓
- **Placeholders:** none — full code/commands. The canned-data risk (clean draft must pass the real mechanical gates) is flagged with explicit STOP-and-report. ✓
- **Type/name consistency:** `run_writing_round(brief, run_dir, round_index, revision_history, author_client, expert_client)` and `run_writing_loop(brief, run_dir, max_rounds, author_client, expert_client)` (Task 1); the endpoint uses `DraftRunner`/`DraftRequest` and the existing `jobs` registry + `GET /jobs/{id}` (M2b). `create_app` gains `draft_runner` additively (existing callers unaffected). Reuses `SequencedFakeClient` (M2b) + `ensure_engine_write_on_path` (M6a). ✓
