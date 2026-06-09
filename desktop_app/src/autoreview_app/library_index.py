from __future__ import annotations

from pathlib import Path


def list_papers(library_dir: Path) -> list[str]:
    """Return sorted paper ids = names of visible subdirectories in the library.

    A paper id is one subdirectory of the library (e.g. ``S01``). Returns an
    empty list if the directory is missing or has no paper subdirectories.
    """
    if not library_dir.is_dir():
        return []
    return sorted(
        child.name
        for child in library_dir.iterdir()
        if child.is_dir() and not child.name.startswith(".")
    )
