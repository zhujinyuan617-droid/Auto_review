# AI Guide for Document Decomposer

This guide is for future AI agents working in this project. Read it before changing code or running batch jobs.

## Current Truth

Project root:

```text
Document_Decomposer
```

Main pipeline:

```text
PDF
-> ingest manifest / staged PDF
-> Docling JSON/Markdown
-> clean paper package
-> ai_sections.json
-> reading_blocks.json / reading.md
-> literature_card.json
-> evidence_atoms.json
-> paper_syntheses.json
-> matrix / review draft
```

The mainline tools are Docling, local Python scripts, and an OpenAI-compatible AI endpoint. GROBID, Marker, and PaperQA are historical experiments, not the current mainline.

## Non-Negotiable Rules

- Do not print or expose `config/ai.local.json`, API keys, or auth tokens.
- Do not manually edit generated JSON just to make validation pass.
- If output is bad, fix the prompt, script logic, or validator, then rerun.
- Keep Docling-derived source evidence intact. `content_blocks.json` is the bottom evidence layer.
- Every source block must be represented exactly once in `reading_blocks.json`, except when a validator explicitly reports a source-layer issue.
- `literature_card.json` must cite evidence with `reading_block_id`, `source_block_ids`, `page_start`, `page_end`, and a short exact quote.
- `evidence_atoms.json` is the hard evidence layer. Each atom must cite one `reading_block_id`, use valid `source_block_ids`, and keep `quote` as exact source text.
- `paper_syntheses.json` is the article-internal inference layer. It must cite `evidence_atom_id` values only; it must not cite reading blocks directly.
- Do not merge article-internal synthesis prompts into the literature-card prompt. Keep hard evidence, literature-card extraction, and synthesis separate.
- Prefer batch execution and validation in sub-agents or background logs. Keep the main conversation focused on decisions, summaries, and exceptions.

## Directory Roles

```text
data/docling/json        S01-S05 Docling JSON inputs
data/docling/md          S01-S05 Docling Markdown inputs
data/docling_validation  S06-S13 Docling JSON/Markdown inputs
data/ingest              PDF ingest manifest and staged stable PDF names
library                  Current generated paper packages
reports                  Quality reports and regression records
schemas                  JSON schemas
scripts                  CLI entry points
src/docdecomp            Reusable implementation modules
envs/docling             Local Docling runtime used by run_from_paper_downloads.py
DOCLING_INSTALL.md       Docling install and rebuild instructions
tool_bakeoff             Historical tool comparison workspace, archived outside active project
```

PDF originals live outside this project in:

```text
..\paper_pool\paper
```

When building clean packages, pass this directory with `--pdf-dir` so each paper package gets its own `source.pdf` and `source_pdf.json`.

Compatibility note: the old `paper_downloder` project is historical and should
not be used as a default source. New scripts read `..\paper_pool\paper`; pass
any legacy path explicitly only for archival recovery.

## Standard Commands

Register downloaded PDFs with hash dedupe and stable staged names:

```powershell
py scripts\ingest_paper_downloads.py --source-dir ..\paper_pool\paper
```

Dry-run the full upstream entry point from registered PDFs:

```powershell
py scripts\run_from_paper_downloads.py `
  --paper-id S14 `
  --skip-ingest `
  --dry-run `
  --baseline reports\manual_article_synthesis_baseline.json
```

Run from registered PDFs through Docling and the full post-Docling pipeline:

```powershell
py scripts\run_from_paper_downloads.py `
  --paper-id S14 `
  --skip-ingest `
  --baseline reports\manual_article_synthesis_baseline.json
```

Build clean packages from Docling output:

```powershell
py scripts\build_clean_package.py `
  --json-dir data\docling\json `
  --md-dir data\docling\md `
  --output-dir library `
  --pdf-dir ..\paper_pool\paper `
  --report reports\clean_package_S01_S05.csv
```

For S06-S13 Docling validation inputs:

```powershell
py scripts\build_clean_package.py `
  --json-dir data\docling_validation `
  --md-dir data\docling_validation `
  --output-dir library `
  --pdf-dir ..\paper_pool\paper `
  --report reports\clean_package_S06_S13.csv
```

Run section organization for one paper:

```powershell
py scripts\ai_organize_sections.py --paper-id S01 --library-dir library
```

Build reading blocks:

```powershell
py scripts\ai_build_reading_blocks.py --paper-id S01 --library-dir library
```

Rebuild reading outputs from an existing plan without calling AI:

```powershell
py scripts\ai_build_reading_blocks.py --paper-id S01 --library-dir library --from-plan
```

Build a literature card:

```powershell
py scripts\ai_build_literature_card.py --paper-id S01 --library-dir library --max-ai-attempts 2
```

Build hard evidence atoms:

```powershell
py scripts\ai_build_evidence_atoms.py --paper-id S01 --library-dir library --max-ai-attempts 3
```

Build article-internal syntheses:

```powershell
py scripts\ai_build_paper_syntheses.py --paper-id S01 --library-dir library --max-ai-attempts 4
```

Build article-internal syntheses with manual baseline coverage and canonicalized stable output:

```powershell
py scripts\ai_build_paper_syntheses.py `
  --paper-id S01 `
  --library-dir library `
  --baseline reports\manual_article_synthesis_baseline.json `
  --max-ai-attempts 4
```

Run the stage-ordered pipeline runner:

```powershell
py scripts\run_pipeline.py `
  --paper-id S01 `
  --stage all `
  --pdf-dir ..\paper_pool\paper `
  --baseline reports\manual_article_synthesis_baseline.json
```

`--stage all` runs clean package, sections, reading blocks, literature card, evidence atoms, article-internal syntheses, and final validators. Use `--baseline` when you want stable baseline-covered `paper_syntheses.json`.

Validate reading blocks:

```powershell
py scripts\validate_reading_blocks.py --library-dir library --report reports\reading_blocks_quality.csv
```

Validate literature cards:

```powershell
py scripts\validate_literature_card.py --library-dir library --report reports\literature_card_quality.csv
```

Validate evidence atoms:

```powershell
py scripts\validate_evidence_atoms.py --library-dir library --report reports\evidence_atoms_quality.csv
```

Validate paper syntheses:

```powershell
py scripts\validate_paper_syntheses.py --library-dir library --report reports\paper_syntheses_quality.csv
```

Audit synthesis coverage and repeated-output stability against a manual baseline:

```powershell
py scripts\audit_synthesis_stability.py `
  --paper-id S01 `
  --paper-id S02 `
  --paper-id S03 `
  --syntheses-name paper_syntheses.json `
  --baseline reports\manual_article_synthesis_baseline.json `
  --report reports\synthesis_baseline_final.csv `
  --summary reports\synthesis_baseline_final.json
```

## Concurrency and Batch Safety

The workflow is stage-ordered within each paper, but many papers can run in parallel.

Required order for one `paper_id`:

```text
ingest_paper_downloads
-> Docling conversion
-> run_from_paper_downloads
-> run_pipeline
```

Inside `run_pipeline.py`, the order is:

```text
build_clean_package
-> ai_organize_sections
-> ai_build_reading_blocks
-> ai_build_literature_card
-> ai_build_evidence_atoms
-> ai_build_paper_syntheses
-> validators
```

Safe to run in parallel across different `paper_id` values:

- `ingest_paper_downloads.py` only as a single writer to the manifest; do not run two ingest writers concurrently.
- `run_from_paper_downloads.py` across different `paper_id` values only when they do not share manifest writes and do not write the same Docling output.
- `ai_organize_sections.py`
- `ai_build_reading_blocks.py`
- `ai_build_reading_blocks.py --from-plan`
- `ai_build_literature_card.py`
- `ai_build_evidence_atoms.py`
- `ai_build_paper_syntheses.py`
- Read-only validation, as long as each process writes a different report path

Do not run these concurrently for the same `paper_id`:

- Two `ingest_paper_downloads.py` jobs writing the same manifest.
- Two `run_from_paper_downloads.py` jobs writing the same Docling output.
- Two `build_clean_package.py` jobs writing the same `library/Sxx`.
- `build_clean_package.py` and any downstream AI step for the same `Sxx`.
- Two `ai_organize_sections.py` jobs for the same `Sxx`.
- Two `ai_build_reading_blocks.py` jobs for the same `Sxx`.
- Two `ai_build_literature_card.py` jobs for the same `Sxx`.
- Two `ai_build_evidence_atoms.py` jobs for the same `Sxx`.
- Two `ai_build_paper_syntheses.py` jobs for the same `Sxx`.

Report files need a single writer. If running validators concurrently, write separate temporary reports and merge later, or run one final validator at the end.

For high-throughput runs, use this pattern:

```text
1. Build all clean packages.
2. Run ai_sections for many paper_id values in parallel.
3. After ai_sections is complete, run reading_blocks for many paper_id values in parallel.
4. After reading_blocks is complete, run literature_card for many paper_id values in parallel.
5. After reading_blocks is complete, run evidence_atoms for many paper_id values in parallel.
6. After evidence_atoms is complete, run paper_syntheses for many paper_id values in parallel.
7. Run one final validator pass for reading_blocks, literature_card, evidence_atoms, and paper_syntheses.
```

If a batch is interrupted:

- Inspect each `library/Sxx` directory for missing stage files.
- Rerun only the missing or failed stage for that `paper_id`.
- If `reading_blocks.plan.json` exists but `reading_blocks.json` or `reading.md` is missing/stale, use `ai_build_reading_blocks.py --from-plan`.
- If `literature_card.json` is missing and `literature_card.failed.json` exists, do not hand-edit the official JSON. Fix prompt/script/validator behavior, then rerun `ai_build_literature_card.py`.
- Do not delete outputs that already passed validation unless the user explicitly asks for a clean rebuild.

## Per-Paper Package Files

Each `library/Sxx/` package may contain:

```text
source.pdf                 Copied original PDF when --pdf-dir is provided
source_pdf.json            PDF provenance, hash, and copy metadata
content_blocks.json        Clean blocks derived from Docling JSON
evidence.json              Evidence manifest for text, figures, tables
metadata_candidates.json   Heuristic metadata extracted from Docling output
content.md                 Simple readable dump of clean blocks
figures/                   Extracted figure images
tables/                    Extracted table CSV/Markdown files
ai_sections.json           AI-assigned logical sections
reading_blocks.plan.json   AI grouping plan for source blocks
reading_blocks.json        Materialized semantic reading blocks
reading.md                 Human-readable reading document
merge_report.json          Reading-block merge and validation summary
literature_card.json       Structured literature review card
evidence_atoms.json        Hard evidence atoms extracted from reading blocks
paper_syntheses.json       Article-internal syntheses supported by evidence atoms
```

## Output Responsibilities

`data/ingest/paper_manifest.json`:

- Built by `scripts/ingest_paper_downloads.py`.
- Tracks downloaded PDFs by SHA-256, original filename/path, staged PDF path, stable `Sxx` id, and possible duplicate hints.
- Exact duplicate PDFs with the same SHA-256 are not assigned new ids.
- Different PDF files that look like the same article are flagged with `possible_duplicate_of`; they are not automatically merged.
- `scripts/run_from_paper_downloads.py` skips possible duplicates by default unless `--include-possible-duplicates` is provided.

`content_blocks.json`:

- Built by `src/docdecomp/package_builder.py`.
- It is the stable evidence base for downstream work.
- Do not edit it manually.

`ai_sections.json`:

- AI decides logical sections from clean blocks.
- If bad, improve `ai_organize_sections.py` prompt or post-validation.

`reading_blocks.plan.json`:

- AI decides which source blocks belong together.
- The script materializes original text; AI does not rewrite the paper.
- `src/docdecomp/reading_blocks.py` repairs coverage if the AI plan misses source blocks.

`reading_blocks.json`:

- Downstream input for literature cards.
- It should have `missing=0`, `duplicate=0`, `incomplete=0`, and `continuation_start=0` in validation.

`literature_card.json`:

- Built from `reading_blocks.json`, not raw Docling JSON.
- AI extracts review-relevant claims, methods, variables, mechanisms, quantitative results, limitations, and fuzzy keywords.
- The script validates evidence references and retries with validator feedback when needed.

`evidence_atoms.json`:

- Built from `reading_blocks.json`.
- AI selects hard evidence units, but the script validates each atom's `reading_block_id`, `source_block_ids`, page numbers, and exact quote.
- This layer should stay close to source text. It is not a synthesis layer.
- If AI fails strict validation, the script may use a conservative rule-based fallback.

`paper_syntheses.json`:

- Built from `evidence_atoms.json`.
- AI proposes article-internal syntheses using only `evidence_atom_id` references.
- The script validates atom references, minimum support, duplicate support, required fields, and unsupported numeric scope values.
- When run with `--baseline reports\manual_article_synthesis_baseline.json`, the script also checks manual theme coverage and canonicalizes output for stable repeated runs.
- The final output is therefore "AI semantic candidate + script validation/canonicalization", not unconstrained AI prose.

## Literature Card Schema Notes

Top-level fields include:

```text
schema_version
paper_id
paper
classification
fuzzy_keywords
core_question
study_design
variables
mechanisms
key_findings
quantitative_results
limitations
review_section_hints
ai_warnings
```

Every claim-like item must include evidence. `fuzzy_keywords` are allowed and useful: they are weak-discovery terms for retrieval, clustering, and review planning. They still need evidence.

Do not create placeholder items. Empty, unknown, unspecified, not specified, N/A, none, and similar filler should be omitted, not preserved.

## Known Repairs Already Built In

- Docling groups are recursively expanded when building clean packages.
- Page headers are detected and excluded from `reading.md`, while the evidence chain stays in JSON.
- Empty-caption figures and tables are preserved.
- Reading-block coverage repair auto-adds source blocks missed by AI plans.
- Validator does not penalize a reading block when the Docling source text itself is visibly incomplete and the reading block mirrors it exactly.
- Literature-card generation retries with validator feedback before writing a failed candidate.
- Evidence-atom generation validates exact quote membership in cited reading blocks.
- Paper-synthesis generation validates atom references and can enforce manual baseline coverage.
- Paper-synthesis canonicalization stabilizes repeated output when a baseline is supplied.
- PDF ingest deduplicates exact files by SHA-256 and flags possible same-paper duplicates by DOI-like filename keys and title-token overlap.
- `run_from_paper_downloads.py` detects `docling` on PATH, then the dedicated local runtime at `envs\docling\Scripts\docling.exe`.
- Rebuild Docling with `DOCLING_INSTALL.md`; do not depend on the archived `tool_bakeoff` environment.
- AI cache metadata is written next to generated outputs as `*.meta.json`.
- Writes use atomic temp-file replacement through `src/docdecomp/io_utils.py`.

## Cleaning Rules

Safe to delete:

- Empty temp directories.
- `*.prompt.json`, `*.failed.json`, and `*.regen.json` once their issue has been fixed in code/prompt and a clean validation report exists.
- Old regression output directories after keeping their report.
- Historical validation copies if the original PDFs still exist in `paper_pool`.

Be careful with:

- `data/docling*`: these are current Docling input layers.
- `data/ingest/paper_manifest.json`: this is the current PDF registration ledger.
- `data/ingest/pdfs`: staged PDFs with stable `Sxx_...` names.
- `library`: this is the current generated package output.
- `reports/regression_*`: these are useful validation records.
- `tool_bakeoff`: historical workspace archived outside the active project. It is not required for mainline runs.

## Next Likely Work

- Decide whether `schema_hint` should be merged into the first system prompt for provider compatibility.
- Expand the ingest manifest from the current smoke subset to the full `paper_pool/paper` directory after reviewing possible duplicates.
- Design and implement matrix export from `literature_card.json`, `evidence_atoms.json`, and `paper_syntheses.json`.
- Design cross-paper synthesis: combine hard evidence and article-internal syntheses across multiple papers.
- If a `tool_bakeoff` empty directory remains in the active project, it is a locked deletion leftover; the content backup is under `_backups`.
