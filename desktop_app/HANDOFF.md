# Desktop App — Handoff (for a fresh / compressed session)

> Read order: repo `CLAUDE.md` (rules) → this file → `desktop_app/README.md`
> (overview + API surface) → the design spec + plans in `docs/superpowers/`.
> Date: 2026-06-09.

## TL;DR

`desktop_app/` is a visual app (local FastAPI in a pywebview window) that **wraps
the `Document_Decomposer` engine without modifying it**. Backend milestones
**M1–M7 are implemented and merged to local `main`**. The desktop test suite is
**119 tests, all passing offline** (`cd desktop_app; .venv\Scripts\python -m pytest -q`)
— AI, network, and OS keychain are all faked in tests. The GUI window, the
PyInstaller installer, and macOS signing are **NOT verified** (need a real
machine). The engine is reused as-is; do engine work in `Document_Decomposer`.

## Git state (IMPORTANT — nothing pushed, docs uncommitted)

- All milestone code is on local **`main`**, merged via fast-forward. main is
  **~66 commits ahead of `origin/main` and NOT pushed** (per the user's rule:
  never push without an explicit ask).
- Every feature branch (`feat/desktop-app-m1` … `m7`, incl. m2a/m2b/m4a/m4b/m6a/
  m6b/m6c) was merged then deleted. There is also a pre-existing local branch
  `connection-layer` (engine work, not ours — leave it).
- **Uncommitted** (user must say "提交" to commit; markdown is git-allowed):
  - The design + plan files under `docs/superpowers/` (spec + 11 plans + roadmap).
  - This session's doc updates: `desktop_app/README.md`, root `CLAUDE.md`, root
    `README.md`, the roadmap status banner, this `HANDOFF.md`, and the memory
    `desktop-app-built.md`.
- Pre-existing **modified, uncommitted** engine files were already dirty at
  session start (`M Document_Decomposer/{AI_GUIDE,HANDOFF,README}.md`,
  `scripts/README.md`, `scripts/interactive_assistant.py`, `src/docdecomp/{ai_client,io_utils}.py`).
  **Not ours — never staged them; leave them.** (Every `git add` was scoped to exact `desktop_app/...` paths.)
- `*.egg-info/`, `dist/`, `build/` are now gitignored (root `.gitignore`).

## How to run / verify

```powershell
cd .\desktop_app
py -m venv .venv                                          # if .venv missing
.venv\Scripts\python -m pip install -e .                 # installs app + runtime deps (pyproject)
.venv\Scripts\python -m pip install -r requirements.txt  # + test deps (pytest, httpx)
.venv\Scripts\python -m pytest -q                        # EXPECT: 119 passed, 1 warning (offline)
.venv\Scripts\python -m autoreview_app.main              # opens the window (manual GUI smoke — NOT done in this env)
```

Env: Windows + PowerShell. `.venv` already exists with deps installed. The lone
pytest warning is a pre-existing httpx/starlette TestClient deprecation — harmless.

## Architecture / key decisions (don't relitigate)

- **Engine unchanged.** `engine_bridge.py` puts the engine on `sys.path` and
  exposes its functions. Bridges (all lazy): `ENGINE_SRC` (= repo/Document_Decomposer/src,
  via `parents[3]`), `ensure_engine_scripts_on_path()` (scripts/),
  `ensure_engine_write_on_path()` (scripts/write/), `ensure_engine_use_on_path()` (scripts/use/).
- **Injected-client pattern (how AI is testable offline).** `ai/stages.py`,
  `writing/loop.py`, `writing/gates.py`, `writing/ideation.py` import engine
  modules and call their functions passing a `client`. Production builds the real
  `OpenAICompatibleClient` (`ai/client.build_ai_client`); tests inject
  `tests/_fake_ai.SequencedFakeClient` (canned dicts in order). The engine's
  monolithic `main()` loops are NOT called — the per-round/stage bodies are
  replicated using the engine's component functions.
- **Network seam (discovery).** Everything HTTP goes through `discovery/transport.Transport`
  (`UrllibTransport` real; `tests/_fake_transport.FakeTransport` for tests).
- **Extractor seam.** `extract/` produces a **Docling-shaped JSON** that the
  engine's `build_clean_package` consumes (the real seam — NOT a clean package
  directly). `PyMuPDFExtractor` is the default; Docling would be a 2nd impl.
- **JSON is truth; SQLite is a rebuildable index.** `store/sqlite_index.py`
  rebuilds from the per-paper card JSON every read. Matches CLAUDE.md "信产物".
- **`create_app(config, import_runner=None, search_runner=None, draft_runner=None)`**
  — runners are injectable so HTTP routes test without AI. Only `_default_import_runner`
  is wired to the real pipeline; `search`/`draft` default to **503 (not configured)**
  — wiring them is deferred work (see below).

## What each milestone delivered (all merged)

- **M1** skeleton: FastAPI + pywebview + `/health`,`/library`,`/`.
- **M2a** offline: PDF → engine clean package via PyMuPDF (`engine_bridge.build_package_from_pdf`).
- **M2b** AI: clean package → `literature_card.json` (sections→reading→card via injected client) + `POST /papers/import` job + `GET /jobs/{id}`.
- **M3** discovery: RIS parse, Crossref search source, source registry, `download_records` (fetch + sha256 dedupe), `POST /discovery/import-ris`, `POST /discovery/search`.
- **M4a** browse: SQLite index, `GET /library/papers`,`/papers/{id}`,`/network`.
- **M4b** groups: author identity + DOI-keyed author store + senior-author clustering, `GET /groups`.
- **M5** single-paper view: `decomposition.assemble_decomposition` + `GET /papers/{id}/decomposition` (reads existing fine-layer JSON; degrades gracefully).
- **M6a** writing gates: `writing/gates.check_draft` (engine citation+style gates), `POST /writing/check`.
- **M6b** writing loop: `writing/loop.run_writing_round`/`run_writing_loop` (author→gates→experts→adjudicator, injected clients), `POST /writing/draft` job.
- **M6c** ideation: `writing/ideation` (candidate angles from edges + concept_index), `GET /writing/angles`.
- **M7** packaging: `pyproject.toml` (installable, no PYTHONPATH hack), `settings.py` (API key in OS keychain via `keyring`), `GET/POST/DELETE /settings/apikey` + `GET /settings/setup-manifest`, and build scaffolding (`packaging/autoreview.spec`, `build.ps1`, `PACKAGING.md`) **labeled UNVERIFIED**.

## Deferred — the genuine remaining work

1. **Wire the default runners to reality:** `search` (Crossref + `UrllibTransport`),
   a real `/download` job feeding `import_pdf`, and `draft` (real brief +
   real clients). Pattern: mirror `_default_import_runner` in `api.py`.
2. **Real writing brief:** the engine's `build_writing_brief.build_brief(args)` is
   importable but takes an `argparse.Namespace` (the engine `main()` runs it as a
   subprocess). M6b's loop takes a brief as input; nothing builds a real one yet.
3. **Fine layer + glossary for NEW imports:** M2b's pipeline stops at the card.
   The existing 261/264 library papers already have `evidence_atoms.json` +
   `paper_syntheses.json`; new imports don't. **Glossary is brand-new** (no engine
   code, no `glossary.json` anywhere — `decomposition.py` already tolerates its absence).
4. **AI angle ranking** (M6c shipped deterministic candidates only; the engine's
   `propose_angles.SYSTEM` prompt ranks/phrases them).
5. **Plugins:** Docling as a 2nd `PdfExtractor`; Sci-Hub (default-off, user mirror)
   + screenshot-download (Windows-only) download plugins. M4b clustering's "C"
   co-authorship signal + ORCID identity (shipped "A"/name only).
6. **Frontend:** only a minimal `frontend/index.html`. Real library/network/reader/
   writing screens are a dedicated frontend pass.
7. **M7 on-machine:** GUI smoke, PyInstaller build (spec needs PyInstaller-6
   `block_cipher` removal + macOS `BUNDLE`), macOS signing/notarization, and
   bundling/relocating the engine so the app doesn't need the monorepo layout.
   All documented in `PACKAGING.md`.

## Bugs found in review + fixed (do NOT reintroduce)

- **SQLite reindex concurrency** (M4a): DROP+CREATE raced under FastAPI's
  threadpool. Fixed: module lock + `CREATE TABLE IF NOT EXISTS` + transactional
  `DELETE`+re-insert (`store/sqlite_index.py`). Same lock+upsert in `groups/store.py`.
- **Shared-constant poison** (M4a `network/edges.py`, M6c `writing/ideation.py`):
  `dict(_EMPTY)` shares nested lists. Fixed: return fresh literals each call.
- **Download filename collision** (M3): two papers with same sanitized stem
  overwrote each other. Fixed: `_unique_path` suffixing.
- **Writing-loop fidelity** (M6b): added `forbidden_claims_next_round` propagation
  + `evidence_gate/style_gate/reviews` audit files to match the engine.
- **`clear_api_key`** (M7): real keyring raises `PasswordDeleteError` when no key;
  wrapped in try/except (the mock had hidden it).

## Engine gotchas that bit the canned-data tests

- `numeric_tokens` strips `S\d+` BEFORE extracting numbers → `[S09]` leaks no
  number (matters for `evidence_gate` canned drafts).
- `normalize_claim_id("C1") == "C0001"` (evidence_gate matches claim_ids this way).
- `citation_gate` passes only bracketed `[S09]`; bare `S09`, `(S09)`, `[S09][S10]`
  adjacency, and `[S09] reports` subject-use all FAIL.
- `decide_gate` → acceptance only if all expert decisions ∈ {minor_revision, accept}
  AND no fatal/major; then `build_revision_plan` returns the acceptance record
  WITHOUT an adjudicator AI call.

## Process used (keep it if continuing)

Per task: TDD (failing test → minimal impl → green → commit), then **two-stage
subagent review** — spec-compliance first, then code-quality — fixing any
Critical/Important before moving on. Each milestone got a final holistic review,
then merged to `main` locally (fast-forward) and the branch deleted. Never pushed.
Followed repo `CLAUDE.md` hard rules (calibrated status claims; commit only on
explicit ask; teaching-style replies in Chinese).

## Open decisions for the user (asked, not yet answered)

- Commit the markdown doc updates (this file + README/CLAUDE.md/roadmap/memory +
  the `docs/superpowers/` design+plans)? Currently uncommitted.
- Push `main` (~66 commits) to `origin`? Currently local-only.
