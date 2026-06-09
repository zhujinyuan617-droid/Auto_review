from __future__ import annotations

from .sources.base import SourcePlugin


class SourceRegistry:
    """Holds discovery/download source plugins; routes by capability."""

    def __init__(self) -> None:
        self._sources: list[SourcePlugin] = []

    def register(self, source: SourcePlugin) -> None:
        self._sources.append(source)

    def all(self) -> list[SourcePlugin]:
        return list(self._sources)

    def searchable(self) -> list[SourcePlugin]:
        return [s for s in self._sources if s.can_search]

    def fetchable(self) -> list[SourcePlugin]:
        return [s for s in self._sources if s.can_fetch]

    def get(self, name: str) -> SourcePlugin | None:
        for s in self._sources:
            if s.name == name:
                return s
        return None
