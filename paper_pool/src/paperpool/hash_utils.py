"""Hashing helpers for PDF identity and dedupe checks."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_pdf_hashes(paths: list[Path]) -> dict[str, list[Path]]:
    hashes: dict[str, list[Path]] = defaultdict(list)
    for path in paths:
        hashes[sha256_file(path)].append(path)
    return dict(hashes)
