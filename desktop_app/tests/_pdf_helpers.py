from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF


def make_pdf(path: Path, pages_text: list[str]) -> Path:
    """Write a tiny PDF; one page per string, the string drawn as text."""
    doc = fitz.open()
    try:
        for text in pages_text:
            page = doc.new_page()
            page.insert_text((72, 72), text)
        doc.save(str(path))
    finally:
        doc.close()
    return path
