from __future__ import annotations

import re
from pathlib import Path

_PAPER_DIR = re.compile(r"^S(\d+)$")


def allocate_paper_id(library_dir: Path) -> str:
    """Return the next free paper id ("S<n>") above the max existing Sxx dir.

    The engine derives a paper id from the Docling JSON filename stem, so this
    only needs to be unique within the library directory. Empty/missing -> "S1".
    """
    max_n = 0
    if library_dir.is_dir():
        for child in library_dir.iterdir():
            if not child.is_dir():
                continue
            match = _PAPER_DIR.fullmatch(child.name)
            if match:
                max_n = max(max_n, int(match.group(1)))
    return f"S{max_n + 1}"
