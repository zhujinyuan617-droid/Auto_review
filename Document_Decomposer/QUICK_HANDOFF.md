# Quick Handoff: End-to-End Check

This file is the fast path for another AI agent or future maintainer to verify the project from a fresh session.

## Start Here

Repository root:

```text
D:\Project\Vibe_coding\Auto_review
```

Document Decomposer root:

```text
D:\Project\Vibe_coding\Auto_review\Document_Decomposer
```

Never print or commit:

```text
Document_Decomposer\config\ai.local.json
paper_pool\paper\
Document_Decomposer\data\
Document_Decomposer\library\
Document_Decomposer\reports\
Document_Decomposer\envs\
```

## Current Known-Good Checks

Use `S05` as the canonical one-paper smoke test.

Current scope:

```text
Default mainline: English journal articles.
Deferred by default: Chinese/non-English papers and non-article files such as subject indexes.
```

`run_from_paper_downloads.py --all` processes English-mainline records only unless `--include-deferred` is supplied. Explicit `--paper-id Sxx` still works for targeted experiments on deferred records.

Known-good final state after the latest optimization:

```text
paper_id: S05
title: Hindered settling velocity and microstructure in suspensions of solid spheres with moderate Reynolds numbers
doi: 10.1063/1.2764109
content_blocks: 191
reading_blocks: 168
ai_sections: ok, 8 sections, 191/191 blocks covered
literature_card: ok, ai_warnings=[]
evidence_atoms: ok, 14 atoms, ai_warnings=[]
paper_syntheses: ok, 4 syntheses, ai_warnings=[]
```

The current larger English batch is also known-good:

```text
S10-S19: 10 English-mainline papers completed through validate.
Final batch validators: validate_reading ok, validate_card ok, validate_evidence_atoms ok, validate_paper_syntheses ok.
AI fallback warnings: none.
Detailed record: BATCH_TEST_HANDOFF.md
Stable commit: 1d1ef3e
```

## 1. Workspace Safety Check

Run from the repository root:

```powershell
git status --short --ignored
```

Expected:

- No modified source files unless you are intentionally editing.
- Local generated folders appear ignored with `!!`.
- `Document_Decomposer/config/ai.local.json` appears ignored if it exists.

If unexpected untracked files appear, do not delete them unless the user asks.

## 2. Python Syntax Check

Run from `Document_Decomposer`:

```powershell
py -m py_compile `
  scripts\ingest_paper_downloads.py `
  scripts\run_from_paper_downloads.py `
  scripts\run_pipeline.py `
  scripts\ai_organize_sections.py `
  scripts\ai_build_reading_blocks.py `
  scripts\ai_build_literature_card.py `
  scripts\ai_build_evidence_atoms.py `
  scripts\ai_build_paper_syntheses.py `
  src\docdecomp\ai_client.py `
  src\docdecomp\paper_profile.py `
  src\docdecomp\literature_card.py `
  src\docdecomp\evidence_synthesis.py
```

If Windows reports `__pycache__` access denied during parallel work, rerun without parallel commands or use `py -B`.

## 3. AI Config Check

Do not print the config file. Run this redacted check from `Document_Decomposer`:

```powershell
@'
from pathlib import Path
from urllib.parse import urlparse
import sys

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "src"))
from docdecomp.ai_client import load_ai_config

cfg = load_ai_config(ROOT)
parsed = urlparse(cfg.base_url)
print("config_status=ok")
print(f"base_url_host={parsed.netloc}")
print(f"base_url_path={parsed.path or '/'}")
print("api_key=set")
print(f"model={cfg.model}")
'@ | py -
```

Known working DeepSeek-compatible config:

```text
base_url_host=api.deepseek.com
base_url_path=/
model=deepseek-v4-flash
```

`https://platform.deepseek.com/v1` is wrong for chat completions and produced HTTP 405.

For non-programmer setup, use the interactive assistant instead:

```powershell
.\start_assistant.bat
```

The assistant config wizard supports:

```text
DeepSeek preset: https://api.deepseek.com, default model deepseek-v4-flash
OpenAI preset: https://api.openai.com/v1
Custom OpenAI-compatible base_url
```

The assistant checks and writes `config\ai.local.json` using normal Python first. It only calls AI after the config is valid.

Non-interactive checks:

```powershell
py scripts\interactive_assistant.py --status
py scripts\interactive_assistant.py --validate-s05
```

## 4. Ingest/Docling Dry Run

Run from `Document_Decomposer`:

```powershell
py scripts\ingest_paper_downloads.py --limit 5 --dry-run
py scripts\run_from_paper_downloads.py --paper-id S05 --skip-ingest --skip-docling --dry-run
py scripts\run_from_paper_downloads.py --all --skip-ingest --skip-docling --dry-run
```

Expected for S05 after the current smoke run:

```text
Missing Docling outputs: none
```

Expected for `--all` on the current smoke subset:

```text
S01 is skipped as deferred_non_article.
S02/S03/S04 are skipped as deferred_non_english.
S05 remains selected as the English-mainline smoke paper.
```

If Docling must run on a new machine, use:

```powershell
py scripts\run_from_paper_downloads.py --paper-id S05 --skip-ingest --skip-pipeline
```

Docling uses:

```text
Document_Decomposer\envs\docling\Scripts\docling.exe
```

The runner sets:

```text
HF_HUB_DISABLE_SYMLINKS=1
HF_HUB_DISABLE_SYMLINKS_WARNING=1
```

This avoids Hugging Face cache symlink privilege failures on Windows.

## 5. End-to-End S05 Pipeline

If `library/S05` already exists and you only want to verify without changing outputs:

```powershell
py scripts\run_pipeline.py --paper-id S05 --stage validate --library-dir library --reports-dir reports
```

If you want to rebuild S05 after Docling outputs exist:

```powershell
py scripts\run_pipeline.py `
  --paper-id S05 `
  --stage all `
  --json-dir data\docling\json `
  --md-dir data\docling\md `
  --library-dir library `
  --reports-dir reports `
  --pdf-dir data\ingest\pdfs `
  --pdf-dir ..\paper_pool\paper `
  --force
```

For lower-risk staged verification, run one stage at a time:

```powershell
py scripts\run_pipeline.py --paper-id S05 --stage clean --json-dir data\docling\json --md-dir data\docling\md --library-dir library --reports-dir reports --pdf-dir data\ingest\pdfs --pdf-dir ..\paper_pool\paper
py scripts\run_pipeline.py --paper-id S05 --stage sections --library-dir library --reports-dir reports --force
py scripts\run_pipeline.py --paper-id S05 --stage reading --library-dir library --reports-dir reports --force
py scripts\run_pipeline.py --paper-id S05 --stage card --library-dir library --reports-dir reports --force
py scripts\run_pipeline.py --paper-id S05 --stage evidence_atoms --library-dir library --reports-dir reports --force
py scripts\run_pipeline.py --paper-id S05 --stage paper_syntheses --library-dir library --reports-dir reports --force
py scripts\run_pipeline.py --paper-id S05 --stage validate --library-dir library --reports-dir reports
```

## 5b. English Batch Validation Check

If local `library/S10` through `library/S19` exists, verify the latest known-good batch without rerunning AI:

```powershell
py scripts\run_pipeline.py `
  --paper-id S10 `
  --paper-id S11 `
  --paper-id S12 `
  --paper-id S13 `
  --paper-id S14 `
  --paper-id S15 `
  --paper-id S16 `
  --paper-id S17 `
  --paper-id S18 `
  --paper-id S19 `
  --stage validate `
  --library-dir library `
  --reports-dir reports
```

Expected:

```text
validate_reading: ok
validate_card: ok
validate_evidence_atoms: ok
validate_paper_syntheses: ok
```

Read `BATCH_TEST_HANDOFF.md` for the paper-by-paper table and the original batch commands.

## 6. Focused Validators

Run from `Document_Decomposer`:

```powershell
py scripts\validate_reading_blocks.py --paper-id S05 --library-dir library --report reports\reading_blocks_quality.csv
py scripts\validate_literature_card.py --paper-id S05 --library-dir library --report reports\literature_card_quality.csv
py scripts\validate_evidence_atoms.py --paper-id S05 --library-dir library --report reports\evidence_atoms_quality.csv
py scripts\validate_paper_syntheses.py --paper-id S05 --library-dir library --report reports\paper_syntheses_quality.csv
```

Expected:

```text
status=ok
unknown ids=0
bad source refs=0
quote_not_found=0
ai_warnings=[]
```

## 7. Inspect S05 Summary

Run from `Document_Decomposer`:

```powershell
$env:PYTHONIOENCODING='utf-8'
@'
from pathlib import Path
import json, sys
sys.path.insert(0, str(Path("src").resolve()))
from docdecomp.literature_card import load_json as load_card_json, validate_card
from docdecomp.evidence_synthesis import load_json, validate_evidence_atoms, validate_paper_syntheses

paper = Path("library/S05")
reading = load_json(paper / "reading_blocks.json")
card = load_card_json(paper / "literature_card.json")
atoms = load_json(paper / "evidence_atoms.json")
synth = load_json(paper / "paper_syntheses.json")
print("reading_blocks", len(reading.get("reading_blocks") or []))
print("card", validate_card(card, reading), "ai_warnings=", card.get("ai_warnings"))
print("atoms", validate_evidence_atoms(atoms, reading), "ai_warnings=", atoms.get("ai_warnings"))
print("synth", validate_paper_syntheses(synth, atoms), "ai_warnings=", synth.get("ai_warnings"))
'@ | py -X utf8 -
```

Expected current S05:

```text
reading_blocks 168
card status ok, evidence_count about 39, ai_warnings=[]
atoms status ok, atom_count 14, ai_warnings=[]
synth status ok, synthesis_count 4, ai_warnings=[]
```

## 8. If Card Or Evidence Falls Back

`literature_card.json` and `evidence_atoms.json` should not normally contain fallback warnings for S05 now.

Bad signs:

```text
fallback:rule_based_literature_card
fallback:rule_based_evidence_atoms
fallback:rule_based_paper_syntheses
quote_not_found_count > 0
missing_evidence_count > 0
review_section_hints empty on a paper with findings/mechanisms
```

Use the diagnostic switch instead of guessing:

```powershell
py scripts\ai_build_literature_card.py --paper-id S05 --library-dir library --output-name literature_card.debug.json --max-ai-attempts 2 --force --save-failed-attempts
py scripts\ai_build_evidence_atoms.py --paper-id S05 --library-dir library --output-name evidence_atoms.debug.json --max-ai-attempts 2 --force --save-failed-attempts
```

Inspect the generated `*.attemptN.failed.json` files. They contain:

```text
candidate
validation
```

After debugging, remove temporary `*debug*`, `*optimized*`, and `*.failed.json` files from `library/S05` unless the user wants to keep them.

## 9. Git Rules

Commit only code and docs.

Do not commit:

```text
config/ai.local.json
data/
library/
reports/
envs/
paper_pool/paper/
```

Before committing:

```powershell
git status --short --ignored
git diff --stat
```

After committing:

```powershell
git push
```

## 10. Current Next Work

Recommended next move:

1. Add requested-paper completeness checks so validators fail if a selected paper never produced required outputs.
2. Redesign metadata extraction before adding more per-publisher or per-paper rules.
3. Metadata design principle: candidates plus provenance, DOI/authoritative confirmation when available, and low-confidence fields left blank or marked `review_required`.
4. Recheck S05/S06/S08/S09 and S10-S19 after the metadata design, without adding individual-paper exceptions.
5. Matrix export and cross-paper synthesis are intentionally postponed.
