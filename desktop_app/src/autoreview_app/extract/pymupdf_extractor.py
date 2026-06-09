from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

from .docling_json import build_docling_json


class PyMuPDFExtractor:
    """Extract text blocks from a PDF using PyMuPDF and shape them as Docling JSON."""

    name = "pymupdf"

    def extract(self, pdf_path: Path) -> dict[str, Any]:
        text_items: list[dict[str, Any]] = []
        doc = fitz.open(str(pdf_path))
        try:
            for page_index in range(doc.page_count):
                page = doc[page_index]
                page_no = page_index + 1
                for block in page.get_text("blocks"):
                    # block = (x0, y0, x1, y1, text, block_no, block_type)
                    x0, y0, x1, y1, text = block[0], block[1], block[2], block[3], block[4]
                    text = (text or "").strip()
                    if not text:
                        continue
                    text_items.append(
                        {
                            "page_no": page_no,
                            "text": text,
                            "bbox": {
                                "l": x0,
                                "t": y0,
                                "r": x1,
                                "b": y1,
                                "coord_origin": "TOPLEFT",
                            },
                        }
                    )
        finally:
            doc.close()
        return build_docling_json(
            name=pdf_path.stem,
            origin_filename=pdf_path.name,
            text_items=text_items,
        )
