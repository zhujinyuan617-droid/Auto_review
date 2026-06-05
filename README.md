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

## Current Next Milestones

1. Push the current local workspace to the `Auto_review` monorepo.
2. Verify a fresh clone on another machine or another folder.
3. Run one-paper end-to-end smoke test before batch processing.
4. After the workflow is stable, design matrix export and cross-paper synthesis.
