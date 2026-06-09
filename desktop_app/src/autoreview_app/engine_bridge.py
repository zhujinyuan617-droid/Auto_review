from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# engine_bridge.py lives at desktop_app/src/autoreview_app/engine_bridge.py.
# parents[3] is the repo root; the engine source is Document_Decomposer/src.
ENGINE_SRC = Path(__file__).resolve().parents[3] / "Document_Decomposer" / "src"
if not ENGINE_SRC.is_dir():
    raise RuntimeError(
        f"Engine source not found at {ENGINE_SRC}; expected Document_Decomposer/src"
    )
if str(ENGINE_SRC) not in sys.path:
    sys.path.insert(0, str(ENGINE_SRC))

from docdecomp.package_builder import build_clean_package  # noqa: E402

from .extract.base import PdfExtractor
from .paper_ids import allocate_paper_id


def _slug(stem: str) -> str:
    # Cosmetic only: the engine parses the paper id from the "S<n>_" filename
    # prefix, not from this slug. Kept short for tidy filenames.
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", stem).strip("_")
    return cleaned[:40].strip("_") or "paper"


def build_package_from_pdf(
    pdf_path: Path,
    library_dir: Path,
    docling_json_dir: Path,
    extractor: PdfExtractor,
) -> str:
    """PDF -> Docling JSON (via extractor) -> engine clean package. Returns paper id.

    The engine derives the paper id from the JSON filename stem, so the file is
    named "<paper_id>_<slug>.json". Fully offline; no AI.
    """
    paper_id = allocate_paper_id(library_dir)
    docling = extractor.extract(pdf_path)

    docling_json_dir.mkdir(parents=True, exist_ok=True)
    json_path = docling_json_dir / f"{paper_id}_{_slug(pdf_path.stem)}.json"
    json_path.write_text(json.dumps(docling, ensure_ascii=False), encoding="utf-8")

    result = build_clean_package(json_path, None, library_dir)
    # The engine derives the id from the filename; it must equal what we allocated.
    assert result.paper_id == paper_id, (
        f"engine returned {result.paper_id!r} but allocated {paper_id!r} "
        f"(json filename {json_path.name!r})"
    )
    return result.paper_id
