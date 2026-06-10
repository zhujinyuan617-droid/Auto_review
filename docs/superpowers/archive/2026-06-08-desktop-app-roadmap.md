# Desktop App — Plans Roadmap (M1–M7)

> **STATUS (2026-06-09): ALL milestones M1–M7 implemented and merged to `main`.**
> Each was built via its own bite-sized plan in `docs/superpowers/plans/` (M4/M6
> split into a/b/c). The desktop suite is **119 tests passing offline** (AI /
> network / keychain faked). NOT verified: the pywebview window, the PyInstaller
> installer, and macOS signing (need a real machine — see `desktop_app/PACKAGING.md`).
> Deferred per each plan's "out of scope": live discovery search/download wiring,
> real writing-brief construction, AI angle ranking, Docling/Sci-Hub/screenshot
> plugins, and the real frontend screens. The per-milestone outlines below are the
> design record; `desktop_app/README.md` is the live status source.

> Organizing index for the desktop-app implementation. Source design: `docs/superpowers/specs/2026-06-08-desktop-app-design.md`.
>
> **How detail works here:** M1 is already a full, line-by-line, TDD plan
> (`2026-06-08-desktop-app-m1-skeleton.md`). M2–M7 are laid out below at
> **task-outline level**. Each is expanded into its own full bite-sized plan
> file **right before it is built**, so later plans rest on what earlier
> milestones actually revealed (clean-package shape, engine call signatures,
> SQLite schema, etc.) instead of guesses.

## Principles carried into every milestone

- **TDD**: failing test → minimal impl → green → commit. Frequent commits.
- **引擎不动**: wrap `docdecomp` / scripts; never rewrite the engine.
- **产物即真理源**: engine JSON stays canonical; SQLite is only a rebuildable index.
- **One plan = working, testable software** on its own.
- **Branch per milestone** (`feat/desktop-app-mN`); no push; user merges after review.
- **Reliable-install principle**: assume all lightweight deps are installed (the
  installer + consent form handle that in M7); only Docling / optional download
  plugins are on-demand.

## Dependency map (build order)

```text
M1 skeleton ──> M2 extraction ──> M4 browse ──> M5 single-paper view
                     │                │              │
                     │                └──> M6 writing core
                     └──> M3 discovery+download (feeds ingest; can overlap M4)
M7 packaging ── depends on everything above (ships the lot)
```

- **M2 before M4**: you must produce real cards before there is anything to browse.
- **M4 before M5/M6**: storage index + browse underpins the reader and writing views.
- **M3** is loosely coupled — it feeds PDFs into M2's ingest; can be built in parallel with M4 once M2's import job exists.
- **M7** is last — it packages and signs the finished app.

---

## M1 — Skeleton (DONE, merged)

- **Plan file:** `docs/superpowers/plans/2026-06-08-desktop-app-m1-skeleton.md`
- **Goal:** double-clickable window ↔ local FastAPI ↔ `/library` (empty list).
- **Status:** implemented + merged. (All M2–M7 below are likewise done — see the status banner up top.)

---

## M2 — Extraction slot (first engine contact)

- **Goal:** import one PDF → produce a real `literature_card.json` via a pluggable extractor, default **PyMuPDF**.
- **Delivers (testable):** `POST /papers/import` runs a background job that turns a chosen PDF into the engine's clean package and a literature card; `/library` then shows that paper.
- **Spec refs:** §5.2 (pluggable extractor), §6.1 (import→usable), §5.4 (jobs).
- **Depends on:** M1 (app + jobs scaffolding).
- **Key new files/modules:**
  - `desktop_app/src/autoreview_app/extract/base.py` — `ExtractorPlugin` interface (`extract(pdf_path) -> CleanPackage`).
  - `desktop_app/src/autoreview_app/extract/pymupdf_extractor.py` — PyMuPDF implementation.
  - `desktop_app/src/autoreview_app/engine_bridge.py` — thin adapter that calls `docdecomp` (reading blocks → card) on a clean package, **without modifying the engine**.
  - `desktop_app/src/autoreview_app/jobs.py` — async job runner + progress (reuse recovery semantics from `run_workflow_with_recovery`).
  - import route added to `api.py`.
- **Main tasks (outline):**
  1. **Pin the clean-package contract**: read `Document_Decomposer/src/docdecomp/package_builder.py` to capture the exact structure the engine consumes; write it down as the `CleanPackage` shape the extractor must emit.
  2. Define `ExtractorPlugin` interface + a contract-test suite (any extractor must satisfy it).
  3. Implement `PyMuPDFExtractor`; make it pass the contract test on a tiny sample PDF.
  4. `engine_bridge`: call the engine to go clean-package → reading blocks → card; assert with existing `validate_*` scripts.
  5. `jobs.py`: background job + progress events; `POST /papers/import` + `GET /jobs/{id}`.
  6. End-to-end smoke: import 1 sample PDF → card produced → `/library` shows it.
- **Risks/unknowns:** the engine's clean-package format must be read from source before coding (do not assume); PyMuPDF output quality vs Docling (contract test guards the shape, quality logged to `ISSUES.md`).
- **Done:** one PDF imported through the UI produces a validated card; contract test green for PyMuPDF.

---

## M3 — Discovery + download layer (plugin framework)

- **Goal:** search OA sources / import citation files → select → batch-download PDFs into the local pool.
- **Delivers (testable):** in-app search (arXiv/OpenAlex) returns results with DOIs; RIS/BibTeX import yields DOIs; selected items download via OA and land in the PDF pool (then flow into M2 ingest).
- **Spec refs:** §5A (whole section), §6.0 (discovery flow).
- **Depends on:** M2 (so downloaded PDFs have an ingest to flow into); can overlap M4.
- **Key new files/modules:**
  - `desktop_app/src/autoreview_app/sources/base.py` — `SourcePlugin` interface v1 (`capabilities`, `search()`, `fetch()`, health) — **freeze this interface first**.
  - `desktop_app/src/autoreview_app/sources/openalex.py`, `crossref.py`, `arxiv.py` — built-in OA sources (search + OA fetch).
  - `desktop_app/src/autoreview_app/sources/registry.py` — plugin discovery/load/enable/disable + isolation boundary.
  - `desktop_app/src/autoreview_app/citation_import.py` — RIS/BibTeX → DOIs (reuse `paper_pool` RIS parsing).
  - `desktop_app/src/autoreview_app/download.py` — priority fetch (OA → user-enabled fallbacks) + dedupe via `paper_pool` SHA-256.
  - discovery/download routes in `api.py`; `GET /sources`, `POST /sources/{id}/config`.
- **Main tasks (outline):**
  1. Freeze `SourcePlugin` interface v1 + contract-test suite (every source must pass).
  2. Plugin registry: load/enable/disable; failure isolation; capability declaration.
  3. Built-in OA sources (search + fetch) against real APIs (politeness: `mailto`/User-Agent, rate limits).
  4. Citation import (RIS/BibTeX) reusing `paper_pool`.
  5. Download orchestration + dedupe; wire to M2 ingest.
  6. Reference plugins **deferred**: Sci-Hub (default-off, user mirror) and screenshot-download (Windows-only) come after the framework is proven.
- **Risks/unknowns:** OA API shape/quotas; the "heavy" plugin framework cost (freeze interface early); Sci-Hub legal posture stays user-side (see §8).
- **Done:** search→select→OA download→dedupe→ingest works for an arXiv sample; `SourcePlugin` contract test green.

---

## M4 — Browse: storage index + library/network screens + research-group clustering

- **Goal:** fast, queryable browsing of the library, the relation network, and auto-grouped research groups.
- **Delivers (testable):** SQLite index built from engine JSON; library screen with group facet; network screen; `groups.json` produced by deterministic clustering (A primary, C auxiliary).
- **Spec refs:** §5.5 (storage/index), §5.6 (screens 1–2), §5B (research-group clustering), §6.1 last step.
- **Depends on:** M2 (needs real cards/relations to index).
- **Key new files/modules:**
  - `desktop_app/src/autoreview_app/store/sqlite_index.py` — `reindex(library_dir)` + read queries; rebuildable from JSON.
  - `desktop_app/src/autoreview_app/grouping/anchor.py` — pick group anchor (corresponding→last author; configurable).
  - `desktop_app/src/autoreview_app/grouping/identity.py` — resolve identity (OpenAlex id > ORCID > name+affiliation).
  - `desktop_app/src/autoreview_app/grouping/coauthor.py` — co-authorship graph + community (aux path C).
  - `desktop_app/src/autoreview_app/grouping/build_groups.py` — emit `groups.json` with merge evidence + confidence.
  - frontend: library screen (+ group facet), network screen; `GET /groups`, `GET /groups/{id}` routes.
- **Main tasks (outline):**
  1. SQLite index over engine JSON (+ test: rebuild from JSON, query papers/relations).
  2. Anchor + identity resolution (deterministic; tests on fixed metadata samples).
  3. Co-authorship community (aux); merge/flag logic.
  4. `build_groups` → `groups.json` with evidence; index into SQLite.
  5. Library screen + group facet; network screen (interactive graph).
  6. AI adjudication for flagged name-collisions **deferred** within M4 (script clustering first, cached AI second).
- **Risks/unknowns:** clustering inherent uncertainty (naming conventions, name collisions) — mitigated by evidence + manual correction; do not claim "accurate".
- **Done:** clustering is deterministic/reproducible on a fixed sample; browse + group facet usable.

---

## M5 — Single-paper decomposition view (fine layer + glossary + trace)

- **Goal:** click a paper → structured reader: abstract points / intro problems / glossary / analyses→results / result-relations, every item click-traceable to source.
- **Delivers (testable):** `GET /papers/{id}/decomposition` assembles existing fine-layer artifacts + a new glossary; reader screen with click-to-source.
- **Spec refs:** §5C (whole section), §5.6 screen entry.
- **Depends on:** M4 (browse entry + index), M2 (fine layer must be produced at ingest).
- **Key new files/modules:**
  - Engine side: a **glossary builder** + `validate_glossary` (new step producing `glossary.json`) — added to the ingest pipeline; ensure `evidence_atoms.json` + `paper_syntheses.json` are produced (fine layer revival).
  - `desktop_app/src/autoreview_app/decomposition.py` — assemble decomposition payload from `reading_blocks/ai_sections/literature_card/evidence_atoms/paper_syntheses/glossary`, each item carrying a `reading_block` trace pointer.
  - frontend: single-paper reader screen with trace-jump.
- **Main tasks (outline):**
  1. Revive fine-layer extraction in the ingest path (atoms + syntheses produced + validated).
  2. New glossary extraction + `validate_glossary`.
  3. `decomposition` assembler + provenance-integrity test (every item resolves to a reading block).
  4. Reader screen; click-to-source jump; show atom confidence.
- **Risks/unknowns:** fine-layer accuracy (I1, ~7% atom failures) + new glossary quality — mitigated by click-trace + confidence display; extra ingest time/cost.
- **Done:** decomposition view renders for a sample paper; every shown item traces back to a passage.

---

## M6 — Writing core (ideation + interrogation loop + draft & trace)

- **Goal:** the crown-jewel writing assistant: AI surfaces angles → user interrogates → converges → grounded draft with traceable citations through the existing quality gates.
- **Delivers (testable):** writing session API + screens; draft passes the mechanical-citation/style gates; citations click back to source.
- **Spec refs:** §5.6 screens 3–5, §6.2 (writing flow).
- **Depends on:** M4 (index/network for ideation), M5 optional (richer drilldown).
- **Key new files/modules:**
  - `desktop_app/src/autoreview_app/writing/session.py` — session + turn state over the existing writing loop (`scripts/write/run_writing_loop.py`).
  - `desktop_app/src/autoreview_app/writing/gates_bridge.py` — surface gate results to the UI; allow the one tracked citation-format fix only.
  - frontend: ideation screen, writing/interrogation screen, draft & trace screen.
  - routes: `POST /writing/session`, `POST /writing/turn`, `GET /draft/{id}`, `GET /trace/{citation}`.
- **Main tasks (outline):**
  1. Ideation endpoint over network/cards.
  2. Session/turn state machine bridging the existing writing loop.
  3. Gate bridge (block reasons to UI; no UI bypass of gates).
  4. Draft & trace screen; citation→source jump.
- **Risks/unknowns:** long async AI turns (progress UX); must not let the UI edit accepted artifacts or bypass gates.
- **Done:** a short review drafted in-app passes the gates with traceable citations.

---

## M7 — Polish & packaging (ships the app)

- **Goal:** turn the working app into something a forum user installs and runs on Windows/macOS.
- **Delivers:** settings/keychain UI; Docling on-demand install; cross-platform package + signing; consent-form installer; empty-library onboarding.
- **Spec refs:** §4 (install & deps), §5.7 (shell/packaging), §5.8 (keychain), §10 (risks).
- **Depends on:** all of M1–M6.
- **Key work areas:**
  - Settings screen + `keyring` integration (BYO API key); extractor switch.
  - Docling on-demand installer (download + hash/signature verify).
  - Consent form listing lightweight deps installed at setup; refuse → not usable.
  - PyInstaller (or equivalent) packaging for Windows + macOS; **macOS notarization**.
  - Empty-library first-run onboarding (key → first search/import).
- **Risks/unknowns:** cross-platform packaging + macOS signing/notarization are the main engineering cost; Docling download mechanics.
- **Done:** a clean machine can install via the package, accept the consent form, add a key, and run end to end.

---

## How we proceed

1. Execute **M1** (full plan exists).
2. Before starting each later milestone, **expand its outline above into a full
   bite-sized plan file** (`2026-06-08-desktop-app-mN-<name>.md`), informed by
   what the previous milestones revealed.
3. Review/merge each milestone branch before moving on.
