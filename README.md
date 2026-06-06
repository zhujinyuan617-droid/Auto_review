# Auto Review

Auto Review is a two-part literature workflow:

```text
paper_pool
  -> PDF intake, download, Zotero scan, dedupe, and pool governance

Document_Decomposer
  -> PDF ingest, Docling conversion, reading blocks, literature cards,
     evidence atoms, and article-internal syntheses
```

The main design rule is to keep intake, evidence extraction, and synthesis as
separate layers. `paper_pool` decides whether a PDF can enter the formal pool.
`Document_Decomposer` turns formal PDFs into structured evidence packages.

Current processing scope is intentionally narrow: the default Document
Decomposer mainline is English journal articles. Chinese/non-English papers and
non-article files are kept as deferred records for later targeted work.

## Repository Layout

```text
Auto_review
+-- paper_pool
+-- Document_Decomposer
```

This repository is the main monorepo:

- <https://github.com/zhujinyuan617-droid/Auto_review>

Older standalone repositories for `paper_pool` and `Document_Decomposer` may
exist as historical backups, but new work should be managed here.

## Data Flow

```text
Zotero / downloader / manual PDF drops
        |
        v
paper_pool\paper
        |
        v
Document_Decomposer ingest
        |
        v
library\Sxx packages
        |
        v
reading_blocks.json
literature_card.json
evidence_atoms.json
paper_syntheses.json
```

## What Belongs In Git

Commit source code, schemas, tests, config examples, and Markdown docs.

Do not commit generated data or machine-local data:

- PDF pools: `paper_pool/paper/`, `*.pdf`, `*.zip`
- local downloader assets: `paper_pool/user/`
- generated state and reports: `state/`, `reports/`, `data/`, `library/`
- virtual environments: `.venv/`, `venv/`, `envs/`
- local secrets/config: `.env`, `*.local.json`, `config/ai.local.json`

## Quick Start: Paper Pool

```powershell
cd .\paper_pool
py -m pip install -r requirements.txt
py .\scripts\paper_downloader.py init-config
py .\scripts\paper_downloader.py calibrate
py .\scripts\paper_downloader.py vision-test
```

The downloader uses image-template button detection. Fixed screen coordinates
are not required. Machine-local templates are saved under
`paper_pool/user/screensnap/`.

## Quick Start: Document Decomposer

```powershell
cd .\Document_Decomposer
py scripts\ingest_paper_downloads.py --source-dir ..\paper_pool\paper --dry-run
```

Docling uses the local runtime under `Document_Decomposer/envs/docling/` when
available. See `Document_Decomposer/DOCLING_INSTALL.md` to rebuild it on a new
machine.

For another AI agent or a fresh session, read the current project handoff:

```text
Document_Decomposer\HANDOFF.md
```

For a user-friendly menu, double-click:

```text
Document_Decomposer\start_assistant.bat
```

## Current Next Milestones

The cross-paper **link network** + ideation + grounded drafting are now **built
(architecture v2)**: slim cards (metadata + tags + a coarse summary), an
IDF-recalled / AI-typed relation graph, a concept→passage index, and quote-grounded
drafting. See `Document_Decomposer/CONNECTION_PLAN.md` (route + v2 status) and
`Document_Decomposer/ISSUES.md` (known limits). Open next steps:

1. Provide the user's own past papers as a writing-style corpus (to close the
   style loop in drafting; see ISSUES I11).
2. Polish: vocabulary non-determinism (I12) and spot-check over-flagging (I13).
3. Reduce hand-written metadata rules; keep the English-paper workflow stable.
