# Document Decomposer Handoff

This is the current handoff snapshot. For the fastest reproducible check, read `QUICK_HANDOFF.md` first. For durable operating rules and broader commands, read `AI_GUIDE.md`.

## Current Pipeline

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

The architecture principle is:

```text
AI makes semantic judgments.
Scripts execute, validate, repair, write atomically, cache AI calls, and stabilize final outputs.
```

Do not hand-edit generated JSON to pass validation. Fix prompt, script logic, validation, fallback, or canonicalization, then rerun.

## Current Known-Good Smoke Set

The active one-paper smoke test is:

```text
library/S05
```

Known-good S05 status:

```text
title: Hindered settling velocity and microstructure in suspensions of solid spheres with moderate Reynolds numbers
year: 2007
doi: 10.1063/1.2764109
content_blocks: 191
evidence_items: 191
ai_sections: 8 sections, 191/191 blocks covered
reading_blocks: 168, 191/191 source blocks covered
literature_card: ok, ai_warnings=[]
evidence_atoms: ok, 14 atoms, ai_warnings=[]
paper_syntheses: ok, 4 syntheses, ai_warnings=[]
```

S05 proved the current end-to-end route:

```text
PDF -> Docling -> clean -> sections -> reading -> card -> evidence_atoms -> paper_syntheses
```

## Current Repository State

This project is now managed in the monorepo:

```text
https://github.com/zhujinyuan617-droid/Auto_review
```

The local repository is a Git repo on branch `main`. Generated data remains local and ignored.

Recent important commits:

```text
9301cd8 Create Auto Review monorepo
3b21c42 Handle UTF-8 console output in decomposer CLIs
e781084 Disable Hugging Face symlinks for Docling on Windows
c7dbda5 Skip library index refresh during pipeline dry runs
74fb232 Improve AI configuration errors
01e78c6 Improve card and evidence AI extraction
```

## Important Files

Implementation modules:

```text
src/docdecomp/package_builder.py
src/docdecomp/reading_blocks.py
src/docdecomp/literature_card.py
src/docdecomp/evidence_synthesis.py
src/docdecomp/ai_client.py
src/docdecomp/ai_cache.py
src/docdecomp/io_utils.py
src/docdecomp/library_index.py
```

AI scripts:

```text
scripts/ingest_paper_downloads.py
scripts/run_from_paper_downloads.py
scripts/ai_organize_sections.py
scripts/ai_build_reading_blocks.py
scripts/ai_build_literature_card.py
scripts/ai_build_evidence_atoms.py
scripts/ai_build_paper_syntheses.py
```

Validators and auditors:

```text
scripts/validate_reading_blocks.py
scripts/validate_literature_card.py
scripts/validate_evidence_atoms.py
scripts/validate_paper_syntheses.py
scripts/audit_synthesis_stability.py
```

Runner:

```text
scripts/run_pipeline.py
```

Current runner status:

```text
--stage all includes clean, sections, reading, card, evidence_atoms, paper_syntheses, and final validators.
--dry-run prints planned commands and does not refresh library/index.csv.
```

## Stage Responsibilities

`ingest_paper_downloads.py`

- Input: downloaded PDFs, usually `..\paper_pool\paper`
- Output: `data/ingest/paper_manifest.json`, `data/ingest/pdfs/Sxx_*.pdf`, `reports/paper_ingest_report.csv`
- Script role: compute SHA-256, skip exact duplicate files, assign stable `Sxx` ids to new PDFs, flag possible same-paper duplicates by DOI-like filename keys and token overlap.

`run_from_paper_downloads.py`

- Input: ingest manifest and staged PDFs.
- Output: missing Docling JSON/Markdown, then normal `library/Sxx` packages through `run_pipeline.py`.
- Script role: check Docling availability, run Docling for missing outputs, copy outputs into `data/docling/json` and `data/docling/md`, call `run_pipeline.py`.
- Docling runtime: defaults to PATH `docling`, then `envs/docling/Scripts/docling.exe`; see `DOCLING_INSTALL.md`.
- Windows compatibility: sets Hugging Face symlink-disabling env vars before launching subprocesses.
- Safety rule: records with `possible_duplicate_of` are skipped unless `--include-possible-duplicates` is provided.

`ai_organize_sections.py`

- Input: `content_blocks.json`, `metadata_candidates.json`
- Output: `ai_sections.json`
- AI role: assign clean blocks to logical paper sections.
- Script role: validate coverage and unknown ids.

`ai_build_reading_blocks.py`

- Input: `content_blocks.json`, `ai_sections.json`
- Output: `reading_blocks.plan.json`, `reading_blocks.json`, `reading.md`, `merge_report.json`
- AI role: plan semantic grouping of Docling layout blocks.
- Script role: materialize text from source blocks, repair coverage, merge obvious continuations, render reading markdown.

`ai_build_literature_card.py`

- Input: `reading_blocks.json`, `metadata_candidates.json`
- Output: `literature_card.json`
- AI role: extract review-card fields with exact evidence quotes.
- Script role: normalize fields, repair missing evidence where a direct matching reading block exists, validate evidence references, retry with validator feedback, fallback if needed.
- Debug option: `--save-failed-attempts` writes failed candidates with validation summaries.

`ai_build_evidence_atoms.py`

- Input: `reading_blocks.json`
- Output: `evidence_atoms.json`
- AI role: select hard evidence atoms.
- Script role: validate atom ids, reading block ids, source ids, pages, exact quote membership, and repair near-miss quotes to exact substrings from the cited reading block when safe.
- Debug option: `--save-failed-attempts` writes failed candidates with validation summaries.

`ai_build_paper_syntheses.py`

- Input: `evidence_atoms.json`
- Output: `paper_syntheses.json`
- AI role: propose article-internal syntheses using evidence atom ids only.
- Script role: validate support, enforce numeric scope support, optionally enforce baseline coverage, canonicalize final stable output.

## AI Configuration

Do not print `config/ai.local.json`.

The local working configuration uses an OpenAI-compatible DeepSeek endpoint. The key is local only.

Known working redacted values:

```text
base_url: https://api.deepseek.com
model: deepseek-v4-flash
```

`https://platform.deepseek.com/v1` produced HTTP 405 and should not be used as the chat-completions base URL.

The AI config loader rejects missing values and unedited placeholders from `config/ai.example.json`.

## Current Commands To Recheck

Use `QUICK_HANDOFF.md` for the complete step-by-step smoke check.

Minimal S05 validation:

```powershell
cd D:\Project\Vibe_coding\Auto_review\Document_Decomposer
py scripts\run_pipeline.py --paper-id S05 --stage validate --library-dir library --reports-dir reports
```

Focused validators:

```powershell
py scripts\validate_reading_blocks.py --paper-id S05 --library-dir library --report reports\reading_blocks_quality.csv
py scripts\validate_literature_card.py --paper-id S05 --library-dir library --report reports\literature_card_quality.csv
py scripts\validate_evidence_atoms.py --paper-id S05 --library-dir library --report reports\evidence_atoms_quality.csv
py scripts\validate_paper_syntheses.py --paper-id S05 --library-dir library --report reports\paper_syntheses_quality.csv
```

Diagnostic reruns for prompt problems:

```powershell
py scripts\ai_build_literature_card.py --paper-id S05 --library-dir library --output-name literature_card.debug.json --max-ai-attempts 2 --force --save-failed-attempts
py scripts\ai_build_evidence_atoms.py --paper-id S05 --library-dir library --output-name evidence_atoms.debug.json --max-ai-attempts 2 --force --save-failed-attempts
```

Remove temporary `*debug*`, `*optimized*`, and `*.failed.json` files after diagnosis unless the user wants to preserve them.

## Current Caveats

- Cross-paper synthesis has not been implemented.
- Matrix/review draft export has not been implemented.
- Full `paper_pool/paper` ingest has not yet been run. Only a `--limit 5` smoke ingest exists in the current monorepo workflow.
- Possible duplicates are skipped by default by `run_from_paper_downloads.py`.
- Generated `data/`, `library/`, `reports/`, and local runtimes are ignored and not part of Git history.
- `config/ai.local.json` is ignored and must stay local.
- AI outputs can vary by provider/model. If card/evidence falls back, use `--save-failed-attempts` and adjust prompt/normalization instead of editing generated JSON by hand.

## Do Not Do

- Do not print `config/ai.local.json`, API keys, or auth tokens.
- Do not hand-edit generated JSON to make validators pass.
- Do not let AI invent ids, source refs, paper facts, or unsupported scope numbers.
- Do not collapse `evidence_atoms` and `paper_syntheses` into the literature-card prompt.
- Do not treat `paper_syntheses.json` as cross-paper synthesis. It is article-internal only.
- Do not run two writers for the same `library/Sxx` stage concurrently.
- Do not commit generated data, local PDFs, local configs, or local runtimes.

## Next Work

1. Run the same staged S05 workflow on 2 to 3 more non-duplicate papers.
2. Check whether `literature_card` and `evidence_atoms` avoid fallback on varied papers.
3. Only after those smoke tests pass, run larger batches.
4. Review duplicate policy before full ingest.
5. Build matrix export using `literature_card.json`, `evidence_atoms.json`, and `paper_syntheses.json`.
6. Design cross-paper synthesis as a separate layer.
