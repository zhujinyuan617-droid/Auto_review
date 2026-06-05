# English Batch Test Handoff

This file records the current larger English-mainline batch test so another AI can inspect or continue it quickly.

## Goal

Run a 10-paper English batch through the current pipeline:

```text
Docling -> clean -> sections -> reading -> literature_card -> evidence_atoms -> paper_syntheses -> validate
```

The purpose is to check whether the English workflow remains stable beyond the S05/S06/S08/S09 smoke set.

## Current Baseline

Already validated before this batch:

```text
S05 ok
S06 ok
S08 ok
S09 ok
```

For these papers, `literature_card`, `evidence_atoms`, and `paper_syntheses` validate without fallback warnings after the metadata/review-synthesis quality improvements.

## Batch Strategy

- Scope: English-mainline records only.
- Chinese/non-English and non-article records remain deferred.
- Generated `data/`, `library/`, and `reports/` outputs stay local and are not committed.
- Prefer parallelism across different `paper_id` values.
- Do not run two writers for the same paper/stage concurrently.

## Quality Checks

For each paper, record:

```text
paper_id
title
doi
content_blocks
reading_blocks
literature_card validation
evidence_atoms validation
paper_syntheses validation
card ai_warnings
evidence_atoms ai_warnings
paper_syntheses ai_warnings
review_section_hints count
```

Bad signs:

```text
fallback:rule_based_literature_card
fallback:rule_based_evidence_atoms
fallback:rule_based_paper_syntheses
missing_evidence_count > 0
quote_not_found_count > 0
review_section_hints empty on a paper with findings/mechanisms
```

## Commands

Register selected PDFs with:

```powershell
py scripts\ingest_paper_downloads.py --source-dir "<PDF path>" ...
```

Run staged or all-in-one processing with:

```powershell
py scripts\run_from_paper_downloads.py --paper-id Sxx --skip-ingest
```

Run validation after the batch:

```powershell
py scripts\run_pipeline.py --paper-id Sxx --stage validate --library-dir library --reports-dir reports
```

## Results

Final status: passed after one concurrency fix and one metadata cleanup pass.

```text
Initial all-in-one run:
  py scripts\run_from_paper_downloads.py --paper-id S10 ... --paper-id S19 --skip-ingest --parallel 10

Initial result:
  Docling succeeded for all 10 papers.
  Pipeline completed 8/10 papers.
  S13 and S14 failed at clean while writing library/index.csv on Windows:
    PermissionError: [WinError 5] Access is denied ... .index.csv.tmp-* -> index.csv

Fix:
  src/docdecomp/io_utils.py now retries atomic replace on PermissionError.

Regression check:
  py scripts\run_pipeline.py --paper-id S10 ... --paper-id S19 --stage clean --parallel 10
  Result: 10/10 clean ok.

Final completion:
  S13/S14 were resumed through sections -> reading -> card -> evidence_atoms -> paper_syntheses.
  Final validation run:
    reports/pipeline_20260605_002646_913830_7392_7af66809
  validate_reading: ok
  validate_card: ok
  validate_evidence_atoms: ok
  validate_paper_syntheses: ok
```

Metadata cleanup performed during the batch:

- Avoid treating journal names such as `Microporous and Mesoporous Materials` as article titles.
- Infer Elsevier journal names from `journal homepage` locate keys.
- Infer SPE DOI from filenames such as `168865-PA` as `10.2118/168865-PA`.
- Prefer the filename/docling-name year before first-page citation years.
- Sync corrected metadata into existing literature cards with `--from-card` without calling AI.

Design warning: the metadata cleanup above was a pragmatic batch-stability fix, not the final metadata architecture. Do not keep adding individual paper or publisher exceptions. The next metadata layer should record candidates, provenance, authoritative DOI metadata when available, and low-confidence `review_required` fields instead of forcing uncertain values.

## Final Paper Summary

Validation report counts are from `reports/pipeline_20260605_002646_913830_7392_7af66809`.

| Paper | Title | DOI | Year | Journal | Content blocks | Reading blocks | Card evidence refs | Evidence atoms | Syntheses | Hints | AI warnings | Fallbacks |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| S10 | Deagglomeration of Nanoparticle Aggregates via Rapid Expansion of Supercritical or High-Pressure Suspensions | 10.1002/aic.11887 | 2009 | AIChE Journal | 247 | 229 | 38 | 24 | 5 | 3 | 0 | 0 |
| S11 | Molecular modeling of carbon dioxide transport and storage in porous carbon-based materials | 10.1016/j.micromeso.2012.02.045 | 2012 | Microporous and Mesoporous Materials | 176 | 159 | 56 | 20 | 5 | 3 | 0 | 0 |
| S12 | Analytical representation of micropores for predicting gas adsorption in porous materials | 10.1016/j.micromeso.2012.09.002 | 2013 | Microporous and Mesoporous Materials | 185 | 159 | 47 | 14 | 5 | 3 | 0 | 0 |
| S13 | Adsorption and separation of CO2/CH4 mixtures using nanoporous adsorbents by molecular simulation | 10.1016/j.fluid.2013.10.013 | 2014 | Fluid Phase Equilibria | 128 | 117 | 32 | 20 | 5 | 3 | 0 | 0 |
| S14 | Phase Behavior and Minimum Miscibility Pressure in Nanopores | 10.2118/168865-PA | 2014 | SPE Reservoir Evaluation & Engineering | 195 | 128 | 26 | 15 | 5 | 3 | 0 | 0 |
| S15 | Molecular simulation of natural gas transport and storage in shale rocks with heterogeneous nano-pore structures | 10.1016/j.petrol.2015.06.029 | 2015 | Journal of Petroleum Science and Engineering | 155 | 126 | 28 | 15 | 5 | 3 | 0 | 0 |
| S16 | Molecular simulation of CO2-CH4 competitive adsorption and induced coal swelling | 10.1016/j.fuel.2015.07.092 | 2015 | Fuel | 148 | 136 | 33 | 16 | 5 | 3 | 0 | 0 |
| S17 | A review on capillary condensation in nanoporous media: Implications for hydrocarbon recovery from tight reservoirs | 10.1016/j.fuel.2016.06.123 | 2016 | Fuel | 349 | 318 | 34 | 22 | 5 | 3 | 0 | 0 |
| S18 | Phase behavior and flow in shale nanopores from molecular simulations | 10.1016/j.fluid.2016.09.011 | 2016 | Fluid Phase Equilibria | 193 | 180 | 31 | 20 | 5 | 3 | 0 | 0 |
| S19 | Molecular simulation of displacement of shale gas by carbon dioxide at different geological depths | 10.1016/j.ces.2016.09.002 | 2016 | Chemical Engineering Science | 109 | 108 | 27 | 19 | 5 | 3 | 0 | 0 |

## Notes For The Next AI

- Generated `data/`, `library/`, and `reports/` outputs are local/ignored. Do not commit them.
- The batch proves `--parallel 10` is viable for clean after the atomic replace retry.
- The AI stages completed with DeepSeek-compatible config and produced no fallback warnings on this 10-paper English-mainline sample.
- The reading validator still reports a few continuation-start examples caused by formulas/OCR fragments, but there are no missing, unknown, duplicate, embedded-header, cleanup, or incomplete-paragraph failures.
- Next technical improvement to consider: add a requested-paper completeness check so validators fail loudly if a selected paper never reached a required output stage.
- Next metadata improvement: redesign metadata resolution before expanding heuristic rules.
