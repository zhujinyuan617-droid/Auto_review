from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .ai.stages import run_ai_pipeline
from .engine_bridge import build_package_from_pdf
from .extract.base import PdfExtractor
from .language_gate import check_package_language


def import_pdf(
    pdf_path: Path,
    library_dir: Path,
    docling_json_dir: Path,
    extractor: PdfExtractor,
    client_factory: Callable[[Path], Any],
    progress: Callable[[str], None],
) -> str:
    """PDF -> clean package (M2a) -> language gate -> AI card (M2b). Returns the paper id.

    client_factory is given the paper dir and returns an AI client; this lets the
    real app build one client from config while tests inject a fake seeded from the
    just-built package.
    """
    progress("extracting pdf")
    paper_id = build_package_from_pdf(pdf_path, library_dir, docling_json_dir, extractor)
    paper_dir = library_dir / paper_id
    gate = check_package_language(paper_dir)
    if gate["deferred"]:
        (paper_dir / "language_gate.json").write_text(
            json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        progress("deferred: cjk content (中文文献暂不支持,已搁置)")
        return paper_id
    progress("running ai stages")
    client = client_factory(paper_dir)
    run_ai_pipeline(paper_dir, client)
    progress("done")
    return paper_id
