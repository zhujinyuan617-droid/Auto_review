# Desktop App Frontend — Design Spec

> Date: 2026-06-09. Scope: the full visual frontend for `desktop_app/`, served by
> the existing FastAPI backend and shown in the pywebview window.
> Status: design approved in brainstorming; not yet committed (repo rule: commit
> only on explicit ask).

## Goal

Give the desktop app a usable interface over the engine. Today the frontend is a
single stub page that only prints "藏书 N 篇". This spec designs all six screens
(browse, import, network, groups, writing, settings) as a no-build, single-page
static frontend that talks to the existing HTTP API and never touches the engine
or the filesystem directly.

## Constraints / decisions (locked in brainstorming)

- **Full frontend** scope: all six functional areas are designed here; they ship
  in batches (live screens first).
- **No-build pure static**: HTML + CSS + native ES Modules. No Node, no bundler.
  FastAPI serves `frontend/` as static files. This keeps PyInstaller packaging
  simple and matches the current stub.
- **Single-page shell + hash router + per-screen view modules** (architecture B+C).
- The frontend is **read-through-HTTP only**. It calls existing endpoints; it does
  not import the engine, read files, or build engine paths. Backend stays the seam.

## Architecture

```
desktop_app/frontend/
  index.html        # shell: header + left nav + <main id="view">
  app.js            # hash router: parse location.hash -> dynamic import view -> render
  api.js            # fetch wrapper: base URL, JSON parse, error throw, status mapping
  ui.js             # shared helpers: el(), loading/empty/error states, escape()
  styles.css        # one clean light theme, Chinese UI labels
  views/
    papers.js       # browse list + paper detail + decomposition (core)
    import.js       # import PDF / paste RIS
    network.js      # relation edges list
    groups.js       # research-group clusters
    writing.js      # mechanical gates + candidate angles + draft (partial)
    settings.js     # API key + setup manifest
```

- **Routing**: `app.js` listens to `hashchange`/`load`, parses routes like
  `#/papers`, `#/papers/S09`, `#/papers/S09/decompose`, `#/import`, `#/network`,
  `#/groups`, `#/writing`, `#/settings`. It dynamically `import()`s the matching
  view module and calls `render(container, params)`. Unknown route → papers.
- **View module contract**: each `views/*.js` exports `render(container, params)`.
  Render functions fetch their own data via `api.js` and build DOM. Rendering is
  written so the data→DOM step is a pure function of the JSON (testable, see below).
- **Data**: all via existing endpoints (see endpoint map). No new engine coupling.

## Screen-by-screen design + backend data readiness

Backend readiness is the key reality for a "full frontend": some screens have live
data today, some need a tiny config wire, some need real backend work.

### 🟢 Live today (UI is the only missing piece)

**① Papers — `#/papers`** (core)
- Left: list of 261 papers (title / year / journal / type) from `GET /library/papers`
  (`reindex()` runs on each call, so the index is always fresh). Top search box does
  client-side filtering over the loaded list.
- Click a paper → right detail from `GET /papers/{id}`: card head (title, DOI, year,
  journal), classification tags (objects / methods / domains), summary (objective +
  main findings).
- A "拆解 (decompose)" button → `#/papers/{id}/decompose`, rendered from
  `GET /papers/{id}/decomposition`: abstract points, intro problems, glossary,
  analyses → each analysis's result → relations between results.

**② Import — `#/import`** (works for English)
- Pick a PDF path → `POST /papers/import` returns a job id → poll `GET /jobs/{id}`
  showing progress (extracting → ai stages → done).
- RIS: paste text → `POST /discovery/import-ris` → show parsed records.
- ⚠️ Chinese PDFs hard-crash the import (ISSUES I17). The UI must warn up front:
  "暂不支持中文 PDF,会失败" and not pretend otherwise.

**⑤ Writing (gates only) — `#/writing`**
- Paste a draft → `POST /writing/check` → show citation + style gate results.

**⑥ Settings — `#/settings`**
- Show / set / delete API key via `GET|POST|DELETE /settings/apikey`; show the
  install consent manifest via `GET /settings/setup-manifest`.
- ⚠️ Known disconnect: `build_ai_client` reads `ai.local.json`, NOT keyring, so a key
  entered here does not yet reach the engine. UI labels this "暂未生效" unless the
  keyring wire (below) is done.

### 🟡 Cheap config wire makes them live

**③ Network — `#/network`**
- `GET /network` returns empty because `config.edges_path` is None under `from_env`.
  Pointing it at the existing `Document_Decomposer/reports/connection/edges.json`
  makes it return real edges. MVP renders an edge list (relation type, the two
  papers, counts) with a type filter. Graph visualization is deferred.

**⑤ Writing (angles) — `#/writing`**
- `GET /writing/angles` is empty for the same reason (edges + concept_index None).
  Same config wire (point at `reports/connection/concept_index.json`) makes it live.

### 🔴 Need real backend work (UI present, shows empty/placeholder)

**④ Groups — `#/groups`**
- `GET /groups` clusters by senior author but needs `authors_db` populated. Only the
  per-DOI primitive `save_authors()` exists; there is no library→authors_db populate
  step, and cards may not even carry author names. MVP shows a "需先建作者库" empty
  state. Populating the author store is a separate, later step.

**② Import (search) / ⑤ Writing (draft)**
- `POST /discovery/search` → 503 (no default search runner; needs Crossref +
  UrllibTransport wiring). `POST /writing/draft` → 503 (needs a real writing-brief
  builder + clients). Both: UI present but render a "未接通 (not configured)" panel.

### Endpoint map (screen → endpoints)

| Screen | Endpoints | Readiness |
|---|---|---|
| Papers list/detail/decompose | `GET /library/papers`, `/papers/{id}`, `/papers/{id}/decomposition` | 🟢 |
| Import (PDF) | `POST /papers/import`, `GET /jobs/{id}` | 🟢 (English) |
| Import (RIS) | `POST /discovery/import-ris` | 🟢 |
| Import (search) | `POST /discovery/search` | 🔴 503 |
| Network | `GET /network` | 🟡 config |
| Groups | `GET /groups` | 🔴 author store |
| Writing (check) | `POST /writing/check` | 🟢 |
| Writing (angles) | `GET /writing/angles` | 🟡 config |
| Writing (draft) | `POST /writing/draft` | 🔴 503 |
| Settings | `GET|POST|DELETE /settings/apikey`, `GET /settings/setup-manifest` | 🟢 |

## States: loading / empty / error

Three shared helpers in `ui.js`, used by every view:

- **Loading**: every fetch shows "加载中…" first.
- **Empty**: empty results show a one-line guide, not a blank panel
  (network empty → "关系数据未配置"; groups empty → "需先建作者库").
- **Error**: non-200 / network failure → red error line + a retry button; never a
  white screen. 503 from search/draft is rendered as "功能未接通", distinct from a
  real error.

The frontend reads only through HTTP, so a frontend bug cannot corrupt data; the
worst case is a screen that fails to render and offers retry.

## Backend changes included in this work

Small, engine-untouching wires so the 🟡 screens show real data:

1. **Config paths wire (≈5 lines)**: in `main.py` startup, set `config.edges_path` /
   `config.concept_index_path` to
   `Document_Decomposer/reports/connection/{edges,concept_index}.json` when those
   files exist. Makes Network and Writing-angles live. No engine change.
2. **(Optional, separate step) keyring wire**: change `build_ai_client` to read the
   key from keyring first, falling back to `ai.local.json`, so a key set in Settings
   actually reaches the engine. Small but touches the engine client builder; may be
   skipped in the first batch and the Settings screen labels the key "暂未生效".

Explicitly **out of this work** (separate later plans): author-store population for
Groups, live Crossref search, real writing-brief + draft runner. These screens ship
with UI + empty/placeholder states.

## Testing

- **No frontend test framework** (no-build, YAGNI). Two safety nets instead:
  1. View render functions are written as pure `data(JSON) → DOM` so they can be
     exercised in isolation; rendering logic stays free of fetch/side-effects (fetch
     happens in a thin wrapper that calls the pure renderer).
  2. **Real-machine smoke**: extend today's `_e2e_smoke.py` idea into a
     per-endpoint self-check script that starts the app, hits each screen's
     endpoints, and reports which render. Plus a manual click-through of all six
     screens in the pywebview window (this also finally verifies the M7 "GUI opens"
     item, currently unverified).
- **Backend**: the config-paths wire and the optional keyring wire get pytest cases
  in the existing style (inject temp paths / a fake keyring), added to the current
  119-test suite.

## Out of scope (this spec)

- Graph visualization for the network (edge list only in MVP).
- Author-store population, live search, and live draft generation (separate plans).
- Any framework / build tooling. Any styling beyond one clean light theme.
- Mobile / responsive layout (desktop window only).

## Open follow-ups (tracked, not built here)

- ISSUES I17: Chinese-PDF hard crash → a language gate at import (UI only warns now).
- ISSUES I9: DOI truncation example seen on real run.
- The keyring↔engine-client disconnect (item 2 above) if not done in batch one.
