# Auto Review Desktop

A desktop app that puts a visual face on the Document Decomposer engine: import
papers, browse the structured material, decompose a single paper, cluster papers
by research group, and draft a grounded review through quality gates — driven by
a local FastAPI service shown in a pywebview window.

The engine (`../Document_Decomposer/`) is reused **as-is** via an injected AI
client and a `sys.path` bridge (`engine_bridge.py`); no engine code is modified.

## Status (2026-06-09)

Backend milestones **M1–M7 implemented and merged to `main`**. The desktop test
suite is **154 tests, all passing offline** — verified by
`.venv\Scripts\python -m pytest -q` from `desktop_app/`, with the AI client,
network, and OS keychain all replaced by fakes in tests (no real DeepSeek call,
no network, no real credential written). Scope: this is the `desktop_app` suite
only; it is NOT a full-library rerun of the engine pipeline.

**NOT verified here** (needs a real machine): the pywebview window actually
opening, the PyInstaller installer, and macOS signing/notarization. See
`PACKAGING.md`.

Element-index layer (SP1+SP2: per-paper element extraction with verbatim-anchor
verification, seed->bootstrap->streaming registry, SQLite index, search + stats
screens, CJK language gate at import) is implemented with offline tests; the
real-library bootstrap run and the 20-paper sampling audit have NOT been
executed yet (see docs/superpowers/archive/2026-06-09-element-index-design.md §9).

**Deferred** (each plan's "out of scope" in `../docs/superpowers/plans/`):
wiring discovery search/download to live APIs + a real writing-brief builder + AI
angle ranking; the Docling / Sci-Hub / screenshot plugins.

Pipeline regeneration (SP-Regen) implemented on feature/pipeline-regen: default
chain = 4 AI calls/paper (legacy atoms/syntheses behind --include-legacy-stages),
finding facet + backfill tooling, slim card v3 with element-derived tags,
vocabulary derived from the registry (AI normalization retired), authorship via
OpenAlex + institution registry, parallel extraction. Real-library backfill
batches all executed 2026-06-10 (numbers in ISSUES I18; quality by sampling audits I19-I21).

2026-06-10 additions (same branch, offline tests green — engine 152 / desktop 204):
- **AI parallelism settings**: `app_settings.json` beside the library stores
  flash/pro worker counts (defaults = account caps 2500/500); Settings screen
  edits them; batch runners pick the tier by model name (`settings.parallel_for_model`).
- **SP-Speed bulk matching**: registry normalization is now collect → shortlist →
  **parallel** AI judging → **serial** commit (`bulk_match_elements`); the
  bootstrap tail and `backfill_findings.py` default to it (`--match-mode stream`
  keeps the legacy per-paper path). Real-library acceptance: **3.2 min wall,
  154 calls, 0 dangling** — see `../docs/superpowers/archive/2026-06-10-speed-sp-design.md` §6.
- **SP-Map (feature/map-home)**: knowledge-map home screen — 5 switchable lenses
  (topic/method/material/time/institution), deterministic IDF+label-propagation
  clustering with cached FR layout (incremental placement for new papers),
  arrivals card, ego closeup, reading routes, figure wall, linked facet counts
  in the search screen (`/elements/refine`), nav regrouped to 找/读/写/设置.
  All map math is mechanical (zero AI). Real-library smoke: 261 nodes,
  topic lens 21 clusters, ~1s compute then cached. Browser-side interactions
  NOT yet manually verified (checklist in the SP-Map plan).

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
| Elements | `GET /elements/overview`, `GET /elements/stats`, `GET /elements`, `GET /elements/{facet}/{slug}` (+`/cooccurrence`), `POST /elements/query`, `PUT /elements/{facet}/{slug}`, `POST /elements/bootstrap`, `GET /elements/coverage`, `GET /papers/{id}/elements` |
| Settings | `GET`/`POST`/`DELETE /settings/apikey`, `GET`/`PUT /settings/parallel`, `GET /settings/setup-manifest` |
| Map (home) | `GET /map?lens=`, `POST /map/relayout`, `GET /map/arrivals`, `GET /map/route`, `POST /elements/refine`, `GET /papers/{id}/figures` (+`/{name}`) |

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
.venv\Scripts\python -m pytest -q                        # 154 passed, offline
.venv\Scripts\python -m autoreview_app.main              # opens the window (manual GUI smoke)
```

Default library dir is `./library`; override with the `AUTOREVIEW_LIBRARY_DIR`
env var. Because the app imports the engine by relative path, keep it inside the
monorepo (next to `../Document_Decomposer/`).

## Design record

Historical designs + per-milestone plans are archived under
`../docs/superpowers/archive/` (M1-M7, element-index, pipeline-regen, speed-sp).
Living docs: `../docs/superpowers/specs/2026-06-10-data-framework.md` (data contract)
and the map spec/plan. This README is the human-facing overview; packaging steps +
the on-machine verification checklist are in `PACKAGING.md`.
```
