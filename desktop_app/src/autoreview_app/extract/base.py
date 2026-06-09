from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class PdfExtractor(Protocol):
    """A pluggable PDF backend: PDF in, a Docling-compatible JSON dict out.

    Implementations (PyMuPDF now; Docling later) emit the same JSON shape so the
    engine's build_clean_package can consume either one unchanged.
    """

    name: str

    def extract(self, pdf_path: Path) -> dict[str, Any]:
        ...
