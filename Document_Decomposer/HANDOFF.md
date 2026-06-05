# Document Decomposer Handoff

This is the current handoff snapshot. For durable operating rules and commands, read `AI_GUIDE.md`.

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

## Current Generated Set

The current checked sample library is:

```text
library/S01
library/S02
library/S03
```

Current article-internal evidence/synthesis counts:

```text
S01: 21 evidence_atoms, 5 paper_syntheses
S02: 24 evidence_atoms, 5 paper_syntheses
S03: 22 evidence_atoms, 5 paper_syntheses
```

Current validation reports:

```text
reports/evidence_atoms_quality.csv
reports/paper_syntheses_quality.csv
reports/synthesis_baseline_final.csv
reports/synthesis_stability_rounds_13_15.json
reports/pipeline_20260604_103751_641953_62220_ddca8447
reports/paper_ingest_report.csv
```

Final status:

```text
evidence_atoms: ok for S01-S03
paper_syntheses: ok for S01-S03
synthesis baseline coverage: 5/5 for S01, S02, S03
stability rounds 13-15: signature_jaccard = 1.0 for every adjacent round and paper
runner validate stage: reading/card/evidence_atoms/paper_syntheses all ok for S01-S03
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
--baseline is passed through to ai_build_paper_syntheses.py.
```

Manual synthesis baseline:

```text
reports/manual_article_synthesis_baseline.json
```

Current ingest state:

```text
data/ingest/paper_manifest.json
data/ingest/pdfs
```

Smoke ingest was run with `--limit 5`. It detected exact SHA-256 duplicates for existing S01 and S02, then registered staged PDFs for S14, S15, and S16. S15 is flagged as `possible_duplicate_of: S02` because its DOI-like filename key matches existing Docling input for S02.

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
- Script role: normalize fields, validate evidence references, retry with validator feedback, fallback if needed.

`ai_build_evidence_atoms.py`

- Input: `reading_blocks.json`
- Output: `evidence_atoms.json`
- AI role: select hard evidence atoms.
- Script role: validate atom ids, reading block ids, source ids, pages, and exact quote membership.

`ai_build_paper_syntheses.py`

- Input: `evidence_atoms.json`
- Output: `paper_syntheses.json`
- AI role: propose article-internal syntheses using evidence atom ids only.
- Script role: validate support, enforce numeric scope support, optionally enforce baseline coverage, canonicalize final stable output.

## Current Synthesis Stabilization

The article-internal synthesis layer was calibrated as follows:

1. Manually analyze each paper's evidence atoms.
2. Store expected article-internal themes in `reports/manual_article_synthesis_baseline.json`.
3. Call AI repeatedly to produce `paper_syntheses`.
4. Compare AI output to the manual baseline with `scripts/audit_synthesis_stability.py`.
5. If coverage drifts, adjust prompt/validation/canonicalization and rerun.
6. Final result must pass three consecutive stable rounds.

The final stable run was rounds 13-15:

```text
reports/synthesis_stability_rounds_13_15.csv
reports/synthesis_stability_rounds_13_15.json
```

When using the baseline:

```powershell
py scripts\ai_build_paper_syntheses.py `
  --paper-id S01 `
  --library-dir library `
  --baseline reports\manual_article_synthesis_baseline.json `
  --max-ai-attempts 4
```

The final `paper_syntheses.json` is canonicalized, so it is not raw free-form AI output. It is an AI candidate that passed semantic coverage, then script-normalized into stable theme order, stable support ids, stable claim text, and stable reasoning/scope format.

## Current Commands To Recheck

Validate the current library:

```powershell
py scripts\ingest_paper_downloads.py --limit 5 --dry-run
py scripts\run_from_paper_downloads.py --paper-id S14 --skip-ingest --dry-run --baseline reports\manual_article_synthesis_baseline.json
py scripts\validate_evidence_atoms.py --paper-id S01 --paper-id S02 --paper-id S03 --report reports\evidence_atoms_quality.csv
py scripts\validate_paper_syntheses.py --paper-id S01 --paper-id S02 --paper-id S03 --report reports\paper_syntheses_quality.csv
py scripts\audit_synthesis_stability.py --paper-id S01 --paper-id S02 --paper-id S03 --syntheses-name paper_syntheses.json --baseline reports\manual_article_synthesis_baseline.json --report reports\synthesis_baseline_final.csv --summary reports\synthesis_baseline_final.json
py scripts\run_pipeline.py --paper-id S01 --paper-id S02 --paper-id S03 --stage validate
```

## Current Caveats

- Cross-paper synthesis has not been implemented.
- Matrix/review draft export has not been implemented.
- Full `paper_pool/paper` ingest has not yet been run. Only a `--limit 5` smoke ingest exists.
- S15 is currently flagged as a possible duplicate of S02. Do not process it unless the duplicate decision is reviewed.
- S02 `evidence_atoms.json` was produced by rule-based fallback after AI failed strict evidence validation. This is expected and recorded in `ai_warnings`.
- `schema_hint` is currently appended as an extra system message by `OpenAICompatibleClient.chat_json`. This works, but merging it into the first system message may improve compatibility with some OpenAI-compatible endpoints.
- The project directory is not currently a git repository, so use file-level inspection and reports rather than `git diff`.

## Do Not Do

- Do not print `config/ai.local.json`.
- Do not hand-edit generated JSON to make validators pass.
- Do not let AI invent ids, source refs, paper facts, or unsupported scope numbers.
- Do not collapse `evidence_atoms` and `paper_syntheses` into the literature-card prompt.
- Do not treat `paper_syntheses.json` as cross-paper synthesis. It is article-internal only.
- Do not run two writers for the same `library/Sxx` stage concurrently.

## Next Work

1. Decide whether `schema_hint` should be merged into the first system prompt for provider compatibility.
2. Review `data/ingest/paper_manifest.json`, especially S15's possible duplicate flag.
3. Run full PDF ingest without `--limit` after duplicate policy is accepted.
4. Build matrix export using `literature_card.json`, `evidence_atoms.json`, and `paper_syntheses.json`.
5. Design cross-paper synthesis as a separate layer.
6. Extend from S01-S03 to S04+ only after the current validation gates are kept intact.
