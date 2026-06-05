# Document Decomposer

This project turns downloaded academic PDFs into a structured literature library.

Current main pipeline:

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
-> literature matrix / review draft
```

For AI agents and detailed operating rules, read [AI_GUIDE.md](AI_GUIDE.md) first. For a fast end-to-end verification checklist, read [QUICK_HANDOFF.md](QUICK_HANDOFF.md). For the current handoff snapshot, read [HANDOFF.md](HANDOFF.md).

Directory roles:

- `data/docling/`: raw Docling outputs. Treat these files as read-only source material.
- `data/ingest/`: registered downloaded PDFs, staged stable PDF names, and ingest manifest.
- `src/docdecomp/`: reusable Python code for parsing Docling JSON and building clean packages.
- `scripts/`: command-line entry points for batch processing and validation.
- `library/`: generated clean paper packages.
- `schemas/`: JSON schemas for clean packages, evidence, AI packets, and literature cards.
- `reports/`: generated quality reports.
- `envs/docling/`: local Docling runtime used by `run_from_paper_downloads.py`.
- `DOCLING_INSTALL.md`: how to install or rebuild Docling.
- `tool_bakeoff/`: removed historical tool comparison workspace; Docling now uses `envs/docling/`.

The current production target is a reproducible package workflow that converts Docling output into `library/<paper_id>/` packages with source PDFs, text blocks, figures, tables, evidence manifests, reading blocks, literature cards, hard evidence atoms, and article-internal syntheses.

Current scope:

- The default mainline is English journal articles.
- Chinese/non-English papers and non-article files such as subject indexes are kept in the manifest as deferred records instead of entering default batch runs.
- Explicit `--paper-id Sxx` runs are still allowed for deferred records when doing targeted experiments.
- `--all` in `run_from_paper_downloads.py` means all current English-mainline records unless `--include-deferred` is provided.

Useful entry points:

- `scripts/ingest_paper_downloads.py`: scan `paper_pool/paper`, dedupe by SHA-256, flag possible duplicates by DOI-like filename keys/tokens, assign stable `Sxx` ids, classify the paper profile, and stage PDFs.
- `scripts/run_from_paper_downloads.py`: check/run Docling for missing outputs, then call `scripts/run_pipeline.py`; default batch selection skips deferred non-English/non-article records.
- `scripts/run_pipeline.py`: run the post-Docling document decomposition pipeline.
- `start_assistant.bat`: double-click interactive assistant for local checks, AI setup, S05 validation, dry-runs, staged runs, and AI log diagnosis.
- `scripts/interactive_assistant.py --status`: non-interactive assistant status check for automation.

AI configuration:

- Copy `config/ai.example.json` to `config/ai.local.json` for local use, then fill in `base_url`, `api_key`, and `model`.
- `config/ai.local.json` is ignored by Git and must not be committed.
- Environment variables can override the local file: `DOCDECOMP_AI_BASE_URL`, `DOCDECOMP_AI_API_KEY`, and `DOCDECOMP_AI_MODEL`.
- The interactive assistant can create this config for DeepSeek, OpenAI, or any custom OpenAI-compatible `base_url`.
