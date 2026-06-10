from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ENV_LIBRARY_DIR = "AUTOREVIEW_LIBRARY_DIR"
DEFAULT_LIBRARY_DIRNAME = "library"


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the desktop app."""

    library_dir: Path
    edges_path: Path | None = None
    concept_index_path: Path | None = None

    @property
    def index_db(self) -> Path:
        """SQLite browse index, kept beside the library dir."""
        return self.library_dir.parent / "index.db"

    @property
    def authors_db(self) -> Path:
        """DOI-keyed author store, kept beside the library dir."""
        return self.library_dir.parent / "authors.db"

    @property
    def elements_data_dir(self) -> Path:
        """Element registry + index live under <root>/data/elements (long-lived state)."""
        return self.library_dir.parent / "data" / "elements"

    @property
    def elements_db(self) -> Path:
        return self.elements_data_dir / "elements_index.sqlite"

    @property
    def elements_registry_path(self) -> Path:
        return self.elements_data_dir / "registry.json"

    @property
    def elements_log_path(self) -> Path:
        return self.elements_data_dir / "registry_log.jsonl"

    @property
    def institutions_data_dir(self) -> Path:
        """Institution registry + log live under <root>/data/institutions (long-lived state)."""
        return self.library_dir.parent / "data" / "institutions"

    @property
    def institutions_registry_path(self) -> Path:
        return self.institutions_data_dir / "registry.json"

    @property
    def institutions_log_path(self) -> Path:
        return self.institutions_data_dir / "registry_log.jsonl"

    @classmethod
    def from_env(cls) -> "AppConfig":
        raw = os.environ.get(ENV_LIBRARY_DIR)
        library = Path(raw) if raw else Path.cwd() / DEFAULT_LIBRARY_DIRNAME
        return cls(library_dir=library)
