# GitHub Monorepo Checklist

This workspace is now intended to be managed as one GitHub repository:

```text
Auto_review
+-- paper_pool
+-- Document_Decomposer
```

Target repository:

```text
https://github.com/zhujinyuan617-droid/Auto_review
```

The older repositories `paper_pool` and `Document_Decomposer` can stay online as
temporary backups until this monorepo has been pushed and smoke-tested. After
that, archive them on GitHub instead of deleting them immediately.

## Current Health Check

Checked on 2026-06-05:

- `Auto_review` exists on GitHub with default branch `main`.
- This local folder is already a Git repo (`.git` present), initialized and
  pushed, with `main` tracking `origin/main`. The initial-push steps below are
  historical and have already been run.
- Local large/generated data exists and must stay out of Git:
  - `paper_pool/paper/` contains hundreds of PDFs.
  - `Document_Decomposer/envs/` contains the local Docling runtime.
  - Generated `data/`, `library/`, `reports/`, and `state/` folders are local outputs.

## Files That Should Be Committed

Commit source code, tests, schemas, docs, and portable config defaults:

```text
README.md
.gitignore
GITHUB_SYNC_CHECKLIST.md
paper_pool/.gitignore
paper_pool/AI_GUIDE.md
paper_pool/README.md
paper_pool/requirements.txt
paper_pool/start_interactive.bat
paper_pool/config/paper_downloader.config.json
paper_pool/scripts/
paper_pool/src/
paper_pool/tests/
Document_Decomposer/.gitignore
Document_Decomposer/AI_GUIDE.md
Document_Decomposer/DOCLING_INSTALL.md
Document_Decomposer/HANDOFF.md
Document_Decomposer/README.md
Document_Decomposer/config/
Document_Decomposer/schemas/
Document_Decomposer/scripts/
Document_Decomposer/src/
```

## Files That Must Stay Out Of Git

The root `.gitignore` is designed to exclude these:

```text
paper_pool/paper/
paper_pool/user/
paper_pool/config/*.local.json
paper_pool/.venv/
Document_Decomposer/envs/
Document_Decomposer/config/ai.local.json
Document_Decomposer/data/
Document_Decomposer/library/
Document_Decomposer/reports/
*.pdf
*.zip
```

## Initial Push Commands (historical — already completed)

The repository has already been initialized and pushed. These commands are kept
only as a record of how the monorepo was first created:

```powershell
cd D:\Project\Vibe_coding\Auto_review
git init
git branch -M main
git remote add origin https://github.com/zhujinyuan617-droid/Auto_review.git
git add .
git commit -m "Create Auto Review monorepo"
git push -u origin main
```

## Routine Sync

For ongoing work, before staging confirm large/local folders still show as
ignored, then commit and push:

```powershell
git status --ignored
git add .
git status
git commit -m "<message>"
git push
```

Check that `paper_pool/paper/`, `Document_Decomposer/envs/`, `*.pdf`,
`*.zip`, `*.local.json`, generated `data/`, `library/`, `reports/`, and
`state/` files are never staged.

## Fresh Clone Smoke Test

After pushing, test from a fresh folder:

```powershell
cd D:\Project\Vibe_coding
git clone https://github.com/zhujinyuan617-droid/Auto_review.git Auto_review_clone
cd Auto_review_clone\paper_pool
py -m unittest tests\test_paper_downloader.py
py .\scripts\paper_downloader.py --config .\config\paper_downloader.config.json doctor
```

Expected:

- unit tests pass
- `doctor` prints paths under the clone
- `doctor` says image templates are missing until `calibrate` is run

Then check Document Decomposer syntax:

```powershell
cd ..\Document_Decomposer
py -m py_compile scripts\ingest_paper_downloads.py scripts\run_from_paper_downloads.py scripts\run_pipeline.py
```

## Archiving Old Repositories

Once the monorepo is pushed and the fresh clone smoke test passes:

1. Open the old `paper_pool` repository on GitHub.
2. Go to Settings.
3. Use "Archive this repository".
4. Repeat for `Document_Decomposer`.

Archiving is safer than deletion because old links still work and the history is
preserved.
