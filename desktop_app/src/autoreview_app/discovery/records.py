from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CitationRecord:
    """A normalized citation: enough to dedupe, display, and fetch a PDF."""

    title: str = ""
    doi: str = ""
    year: str = ""
    journal: str = ""
    authors: tuple[str, ...] = ()
    pdf_url: str = ""  # a direct open-access PDF url when a source provides one

    @property
    def key(self) -> str:
        """Dedup key: normalized DOI if present, else lowercased title."""
        return self.doi.lower() if self.doi else self.title.strip().lower()
