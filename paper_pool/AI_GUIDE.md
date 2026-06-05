# Paper Pool AI Guide

This project is the PDF intake and governance layer.

## Project Boundary

`paper_pool` owns:

- formal literature-body PDF storage in `paper/`
- downloader intake through `scripts/paper_downloader.py`
- Zotero scan reports through `scripts/import_zotero_pdfs.py`
- candidate promotion through `scripts/promote_candidates.py`
- formal pool audits through `scripts/audit_pool.py`

`paper_pool` does not own:

- `Sxx` package ids
- Docling conversion
- `source.pdf` package copies
- reading blocks
- literature cards
- evidence atoms
- article or cross-paper synthesis
- research-topic filtering

Those belong to Document Decomposer or later analysis stages.

## Naming Clarification

Do not confuse these:

```text
paper_downloder
```

Historical old project directory. The directory name is misspelled. Do not use
it as a default source.

```text
paper_pool\scripts\paper_downloader.py
```

Current downloader script inside the new `paper_pool` project. Keep it unless a
planned rename updates all imports, tests, docs, config, state, and batch files.

```text
paper_pool\paper
```

The canonical PDF pool. Document Decomposer should read from this directory.
When running from this repository layout, that path is usually
`..\paper_pool\paper` relative to `Document_Decomposer`.

## Safety Rules

- Never delete or edit Zotero files.
- Never delete files from `paper/` without an explicit user request and a backup.
- Run `scripts\promote_candidates.py` without `--apply` before applying.
- After any `--apply` promotion, run `scripts\audit_pool.py`.
- Treat `candidate_for_pool` as "looks like a literature-body PDF", not as "research-topic relevant".
- Treat Zotero parent metadata as weak context. Overloaded parents are polluted.
- Reports under `reports/` are regenerable; state files under `state/` are current manifests.
- Downloader button detection is image-template based. Do not reintroduce fixed
  screen-coordinate requirements for `run`; use `calibrate` to capture templates
  under `user/screensnap/`, then `vision-test` to verify them.
- Shared downloader defaults live in `config\paper_downloader.config.json`.
  Machine-specific runtime settings belong in `config\paper_downloader.local.json`,
  which is ignored by Git.

## Standard Commands

Refresh Zotero scan:

```powershell
py .\scripts\import_zotero_pdfs.py
```

Plan candidate promotion:

```powershell
py .\scripts\promote_candidates.py
```

Apply promotion:

```powershell
py .\scripts\promote_candidates.py --apply
```

Audit the formal pool:

```powershell
py .\scripts\audit_pool.py
```

Check downloader RIS parsing:

```powershell
py .\scripts\paper_downloader.py preview ".\user\ris\导出的条目.ris" --limit 1
```

Capture and verify downloader image templates:

```powershell
py .\scripts\paper_downloader.py calibrate
py .\scripts\paper_downloader.py vision-test
```

## Current Known State

After the Zotero promotion run on 2026-06-04:

- `paper/` contains 380 PDFs.
- `state\pool_manifest.json` reports 380 unique hashes and zero duplicate hash groups.
- Zotero scan reports 377 Zotero unique hashes already in the pool and one `needs_manual_review` item.
- Pool audit reports one `small_pdf_file`; downstream ingest should inspect or filter unusual index/contents-style PDFs before large Document Decomposer runs.
- The old `paper_downloder` project is historical and should not be used as the
  active workspace.
