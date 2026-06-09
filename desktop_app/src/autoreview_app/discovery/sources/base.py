from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..records import CitationRecord
from ..transport import Transport


@runtime_checkable
class SourcePlugin(Protocol):
    """A discovery/download source. Declares which capabilities it supports."""

    name: str
    can_search: bool
    can_fetch: bool

    def search(self, query: str, transport: Transport, rows: int = 20) -> list[CitationRecord]:
        ...

    def fetch(self, record: CitationRecord, transport: Transport) -> bytes | None:
        ...
