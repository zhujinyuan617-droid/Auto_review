# Auto Review Desktop

A desktop app that puts a visual face on the Document Decomposer engine: import
papers, browse the structured material, decompose a single paper, cluster papers
by research group, and draft a grounded review through quality gates — driven by
a local FastAPI service shown in a pywebview window.

The engine (`../Document_Decomposer/`) is reused **as-is** via an injected AI
client and a `sys.path` bridge (`engine_bridge.py`); no engine code is modified.

## Status (2026-06-09)

Backend milestones **M1–M7 implemented and merged to `main`**. The desktop test
suite is **119 tests, all passing offline** — verified by
`.venv\Scripts\python -m pytest -q` from `desktop_app/`, with the AI client,
network, and OS keychain all replaced by fakes in tests (no real DeepSeek call,
no network, no real credential written). Scope: this is the `desktop_app` suite
only; it is NOT a full-library rerun of the engine pipeline.

**NOT verified here** (needs a real machine): the pywebview window actually
opening, the PyInstaller installer, and macOS signing/notarization. See
`PACKAGING.md`.

**Deferred** (each plan's "out of scope" in `../docs/superpowers/plans/`):
wiring discovery search/download to live APIs + a real writing-brief builder + AI
angle ranking; the Docling / Sci-Hub / screenshot plugins; and the real frontend
screens (only a minimal `frontend/index.html` exists).

## What it does (HTTP API surface)

| Area | Endpoints |
|---|---|
| Health / library / UI | `GET /health`, `GET /library`, `GET /` |
| Import (PDF → card) | `POST /papers/import`, `GET /jobs/{id}` |
| Browse | `GET /library/papers`, `GET /papers/{id}`, `GET /network` |
| Research groups | `GET /groups` |
| Single-paper view | `GET /papers/{id}/decomposition` |
| Discovery | `POST /discovery/import-ris`, `POST /discovery/search` |
| Writing | `POST /writing/check`, `POST /writing/draft`, `GET /writing/angles` |
| Settings | `GET`/`POST`/`DELETE /settings/apikey`, `GET /settings/setup-manifest` |

## Module map (`src/autoreview_app/`)

- `main.py` — starts the FastAPI server thread, then opens the pywebview window.
- `api.py` — all HTTP routes; `create_app(config, import_runner=, search_runner=, draft_runner=)` (runners are injectable so routes test without AI).
- `config.py` — `AppConfig` (library dir + derived index/edges/concept/authors paths).
- `engine_bridge.py` — puts the engine on `sys.path`; `build_package_from_pdf` + `ensure_engine_{scripts,write,use}_on_path()`.
- `extract/` — pluggable PDF extractor; `PyMuPDFExtractor` emits a Docling-shaped JSON the engine consumes.
- `ai/` — `client.py` builds the engine's client; `stages.py` runs sections→reading→card with an injected client.
- `importer.py` — composes package build (M2a) + AI card (M2b). `jobs.py` — background job registry.
- `discovery/` — RIS parser, injectable `Transport`, Crossref source, source registry, download + SHA-256 dedupe.
- `store/sqlite_index.py` — rebuildable browse index over the card JSON. `network/edges.py` — relation-graph reader.
- `groups/` — author identity + DOI-keyed author store + senior-author clustering.
- `decomposition.py` — single-paper decomposition assembler (abstract/intro/glossary/analyses/results/relations, with source anchors).
- `writing/` — `gates.py` (citation/style gates), `loop.py` (author→gates→experts→adjudicator), `ideation.py` (candidate angles from the relation graph).
- `settings.py` — API key in the OS keychain (via `keyring`). `packaging/installer_manifest.py` — install consent manifest.

## Run

```powershell
# from desktop_app/  (Windows PowerShell)
py -m venv .venv
.venv\Scripts\python -m pip install -e .                 # app + runtime deps (pyproject)
.venv\Scripts\python -m pip install -r requirements.txt  # + test deps (pytest, httpx)
.venv\Scripts\python -m pytest -q                        # 119 passed, offline
.venv\Scripts\python -m autoreview_app.main              # opens the window (manual GUI smoke)
```

Default library dir is `./library`; override with the `AUTOREVIEW_LIBRARY_DIR`
env var. Because the app imports the engine by relative path, keep it inside the
monorepo (next to `../Document_Decomposer/`).

## Design record

The full design + per-milestone implementation plans live under
`../docs/superpowers/` (`specs/2026-06-08-desktop-app-design.md` and the
`plans/...-m1..m7...md` files). Those are the authoritative design/route source;
this README is the human-facing overview. Packaging steps + the on-machine
verification checklist are in `PACKAGING.md`.
```
