from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .records import CitationRecord
from .sources.base import SourcePlugin
from .transport import Transport


def _safe_stem(record: CitationRecord, index: int) -> str:
    basis = record.doi or record.title or f"paper{index}"
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", basis).strip("_")
    return (cleaned[:60].strip("_") or f"paper{index}")


def _unique_path(dest_dir: Path, stem: str) -> Path:
    """A non-existing path for stem.pdf, suffixing _1, _2, ... on collision.

    Two distinct papers whose DOI/title sanitize to the same stem must NOT
    overwrite each other (that would lose data and desync the reported sha256).
    """
    candidate = dest_dir / f"{stem}.pdf"
    counter = 1
    while candidate.exists():
        candidate = dest_dir / f"{stem}_{counter}.pdf"
        counter += 1
    return candidate


def download_records(
    records: list[CitationRecord],
    fetchers: list[SourcePlugin],
    transport: Transport,
    dest_dir: Path,
) -> list[dict[str, Any]]:
    """Fetch each record's PDF via the first fetcher that returns bytes; dedupe by SHA-256.

    Per-record status: downloaded | duplicate | no_full_text.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    seen: dict[str, str] = {}  # sha256 -> path
    results: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        data: bytes | None = None
        for fetcher in fetchers:
            if not fetcher.can_fetch:
                continue
            data = fetcher.fetch(record, transport)
            if data:
                break

        if not data:
            results.append({"key": record.key, "status": "no_full_text", "path": None, "sha256": None})
            continue

        digest = hashlib.sha256(data).hexdigest()
        if digest in seen:
            results.append({"key": record.key, "status": "duplicate", "path": seen[digest], "sha256": digest})
            continue

        path = _unique_path(dest_dir, _safe_stem(record, index))
        path.write_bytes(data)
        seen[digest] = str(path)
        results.append({"key": record.key, "status": "downloaded", "path": str(path), "sha256": digest})

    return results
