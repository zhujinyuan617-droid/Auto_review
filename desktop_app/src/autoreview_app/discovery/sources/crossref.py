from __future__ import annotations

from typing import Any
from urllib.parse import quote

from ..records import CitationRecord
from ..transport import Transport

CROSSREF_WORKS_URL = "https://api.crossref.org/works"


class CrossrefSource:
    """Search Crossref for works -> CitationRecords (metadata + DOI). No PDF fetch."""

    name = "crossref"
    can_search = True
    can_fetch = False

    def search(self, query: str, transport: Transport, rows: int = 20) -> list[CitationRecord]:
        data = transport.get_json(CROSSREF_WORKS_URL, {"query": query, "rows": str(rows)})
        items = (data.get("message") or {}).get("items") or []
        return [self._to_record(item) for item in items]

    def fetch_by_doi(self, doi: str, transport: Transport) -> CitationRecord | None:
        """Fetch one work by DOI from Crossref; return a CitationRecord or None."""
        data = transport.get_json(f"{CROSSREF_WORKS_URL}/{quote(doi, safe='/')}", {})
        message = data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, dict):
            return None
        return self._to_record(message)

    def fetch(self, record: CitationRecord, transport: Transport) -> bytes | None:
        return None  # Crossref is metadata-only

    def _to_record(self, item: dict[str, Any]) -> CitationRecord:
        title_list = item.get("title") or []
        journal_list = item.get("container-title") or []
        authors = tuple(
            f"{a.get('family', '')}, {a.get('given', '')}".strip(", ")
            for a in (item.get("author") or [])
            if a.get("family") or a.get("given")
        )
        return CitationRecord(
            title=(title_list[0] if title_list else "").strip(),
            doi=(item.get("DOI") or "").strip(),
            year=_year(item),
            journal=(journal_list[0] if journal_list else "").strip(),
            authors=authors,
        )


def _year(item: dict[str, Any]) -> str:
    for key in ("published", "issued", "published-online", "published-print"):
        parts = ((item.get(key) or {}).get("date-parts") or [[]])
        if parts and parts[0]:
            return str(parts[0][0])
    return ""
