# Paper Pool

This project is the PDF intake and governance layer for the literature workflow.

Its core question is:

```text
Can this PDF enter the formal literature-body PDF pool for Document Decomposer?
```

It does not try to understand the paper's scientific claims. That belongs to
Document Decomposer.

It is responsible for:

- downloading PDFs from authorized sources with `scripts/paper_downloader.py`
- keeping the canonical `paper/` PDF collection
- scanning Zotero PDFs and producing import-cleaning reports
- deduplicating and normalizing PDF sources before Document Decomposer ingests them
- tracking source paths, hashes, file sizes, and review status for candidate PDFs
- keeping supplements, temporary files, failed imports, and uncertain candidates out of `paper/`
- not filtering by research topic; topic usefulness belongs to later reading, card, and synthesis stages

Current canonical PDF directory:

```text
.\paper
```

The previous project directory was named `paper_downloder`. It was a
historical, misspelled downloader project and should not be used as the active
source. New work should use `paper_pool`.

## Boundary

`paper_pool` owns PDF intake:

- sources: downloader, Zotero, manual PDF drops, and future external sources
- exact duplicate detection with SHA-256
- possible duplicate detection with DOI-like keys, filenames, and metadata
- source tracking and import reports
- candidate review before a file is promoted into `paper/`
- stable human-readable filenames for the formal PDF pool
- objective PDF probing: PDF magic, page count, encryption, extractable text, and obvious non-body attachments

`paper_pool` does not own document decomposition:

- no research-topic inclusion/exclusion decisions
- no `S01`/`S02` paper ids
- no `source.pdf` package renaming
- no Docling JSON/Markdown conversion
- no reading blocks
- no literature cards
- no evidence atoms
- no article-internal or cross-paper synthesis

Those stages belong to Document Decomposer.

## Data Flow

```text
Zotero / downloader / manual PDFs
        |
        v
paper_pool intake
  - scan
  - hash
  - dedupe
  - classify candidates
  - report
        |
        v
paper_pool\paper
        |
        v
Document Decomposer
  - Sxx ids
  - Docling
  - source.pdf package copies
  - reading_blocks.json
  - literature_card.json
  - evidence_atoms.json
  - paper_syntheses.json
```

Only `paper_pool\paper` is the formal downstream source. Candidate, rejected,
temporary, or uncertain PDFs should stay outside `paper/`.

`candidate_for_pool` means a PDF looks like a readable literature-body file. It
does not mean the paper is relevant to a specific research question.

## Install

```powershell
py -m pip install -r requirements.txt
```

## Layout

```text
paper_pool
+-- paper
+-- scripts
+-- config
+-- state
+-- reports
+-- data\zotero_import
+-- user\ris
+-- user\screensnap
+-- src\paperpool
+-- tests
+-- AI_GUIDE.md
+-- README.md
```

`user/` is the user-facing drop area. Put RIS exports in `user/ris/`;
machine-local downloader image templates live in `user/screensnap/`.

The old root-level script entrypoints are no longer used. Run scripts from
`scripts/`.

Do not confuse the removed old project directory `paper_downloder` with the
current downloader script `scripts\paper_downloader.py`. The script is still a
valid `paper_pool` intake tool.

## Interactive Menu

```powershell
py .\scripts\interactive.py
```

Or double-click:

```powershell
.\start_interactive.bat
```

## Preview RIS

```powershell
py .\scripts\paper_downloader.py preview ".\user\ris\导出的条目.ris" --limit 5
```

## Initialize Config

```powershell
py .\scripts\paper_downloader.py init-config
```

Default download directory:

```text
.\paper
```

To override it:

```powershell
py .\scripts\paper_downloader.py init-config --download-dir "D:\papers"
```

Paths in downloader config may be absolute or relative to the `paper_pool`
project root. Shared defaults live in `config\paper_downloader.config.json`.
The downloader uses `config\paper_downloader.local.json` by default for
machine-specific settings; that local file is ignored by Git.

## Calibrate Button Templates

Open one sample article page manually, then run:

```powershell
py .\scripts\paper_downloader.py calibrate
```

The tool captures image templates for the View PDF and download buttons. Runtime
button detection is image-based; fixed screen coordinates are not required.
The templates are saved under `user/screensnap/`, which is treated as
machine-local data.

Check the templates before a real run:

```powershell
py .\scripts\paper_downloader.py vision-test
```

The tool uses your own Chrome session and Windows desktop interaction. It does
not bypass login, CAPTCHA, or access control.

## Trial Run

```powershell
py .\scripts\paper_downloader.py run ".\user\ris\导出的条目.ris" --limit 1
```

Dry run:

```powershell
py .\scripts\paper_downloader.py run ".\user\ris\导出的条目.ris" --limit 3 --dry-run
```

## Batch Run

```powershell
py .\scripts\paper_downloader.py run ".\user\ris\导出的条目.ris" --batch-limit 20 --failure-limit 2 --min-delay 10 --max-delay 30
```

## Status Check

```powershell
py .\scripts\paper_downloader.py doctor ".\user\ris\导出的条目.ris"
```

Shared config defaults are stored in `config\paper_downloader.config.json`;
machine-local runtime config is stored in
`config\paper_downloader.local.json`; state is stored in
`state\paper_downloader.state.json`; reports are stored in
`reports\paper_downloader.report.csv`.

## Pool Audit

Audit the formal PDF pool without deleting, renaming, or moving PDFs:

```powershell
py .\scripts\audit_pool.py
```

Dry run:

```powershell
py .\scripts\audit_pool.py --dry-run
```

Outputs:

```text
state\pool_manifest.json
reports\pool_audit_report.csv
reports\pool_audit_summary.md
```

## Zotero Scan

The Zotero cleaning layer starts as a read-only report generator. By default it
scans `%USERPROFILE%\Zotero\storage`, hashes PDFs, compares them with `paper/`,
and uses Zotero DB metadata only as weak context.

It does not copy PDFs, delete files, modify Zotero, or promote candidates into
the formal pool.

Dry run:

```powershell
py .\scripts\import_zotero_pdfs.py --dry-run
```

Write the manifest and CSV report:

```powershell
py .\scripts\import_zotero_pdfs.py
```

Outputs:

```text
state\zotero_import_manifest.json
reports\zotero_import_report.csv
reports\zotero_import_summary.md
data\zotero_import\db_snapshots\zotero_<timestamp>.sqlite
```

The main `status` column answers the import question, while `warnings` keeps
separate risk signals such as `parent_attachment_overload`,
`filename_parent_doi_conflict`, and `zotero_internal_exact_duplicates`.

Current import statuses:

```text
exact_duplicate_in_pool
candidate_for_pool
needs_manual_review
reject_broken_pdf
reject_non_literature_body
```

`document_class` is explanatory metadata, not a research-topic filter. Examples:

```text
main_article
review_article
method_article
thesis_or_dissertation
report_or_preprint
supplement
correction_or_erratum
cover_or_toc
graphical_abstract
unknown
```

## Promote Candidates

Build a promotion plan from the Zotero manifest. Without `--apply`, this only
writes a dry-run plan and does not copy PDFs:

```powershell
py .\scripts\promote_candidates.py
```

Apply the ready candidates into `paper/`:

```powershell
py .\scripts\promote_candidates.py --apply
```

Useful scoped runs:

```powershell
py .\scripts\promote_candidates.py --limit 10
py .\scripts\promote_candidates.py --candidate-id ZOT-4770a4c5d61f
py .\scripts\promote_candidates.py --on-conflict suffix
```

Outputs:

```text
reports\promotion_plan.json
reports\promotion_report.csv
reports\promotion_summary.md
```

Promotion copies files into `paper/`, verifies SHA-256 after copying, and never
deletes or edits Zotero files. Run `py .\scripts\audit_pool.py` after any
`--apply` run.

## Downstream

Document Decomposer should ingest PDFs from:

```text
..\paper_pool\paper
```

Zotero cleaning artifacts live under this project:

```text
scripts\import_zotero_pdfs.py
scripts\audit_pool.py
scripts\promote_candidates.py
data\zotero_import\
reports\pool_audit_report.csv
reports\promotion_report.csv
reports\zotero_import_report.csv
reports\zotero_import_summary.md
```
