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

    @classmethod
    def from_env(cls) -> "AppConfig":
        raw = os.environ.get(ENV_LIBRARY_DIR)
        if raw:
            return cls(library_dir=Path(raw))
        return cls(library_dir=Path.cwd() / DEFAULT_LIBRARY_DIRNAME)
