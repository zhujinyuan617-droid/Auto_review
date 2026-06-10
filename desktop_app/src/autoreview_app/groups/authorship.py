"""Authorship population: OpenAlex (with PDF front-page fallback) + institution registry."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .. import engine_bridge  # noqa: F401 — puts Document_Decomposer/src on sys.path
from docdecomp.element_registry import (  # noqa: E402
    add_alias,
    create_entry,
    find_by_surface,
    load_registry,
    save_registry,
)

_AFF_PATTERN = re.compile(
    r"University|Institute|Laboratory|College|Academy|School of"
)

# Maximum front-page affiliation lines to collect
_MAX_AFFS = 6
# Number of content blocks to scan for affiliations
_SCAN_BLOCKS = 12


def _pdf_fallback_affiliations(paper_dir: Path) -> list[str]:
    """Scan the first _SCAN_BLOCKS content blocks for affiliation-like lines.

    Returns up to _MAX_AFFS unique stripped lines that match _AFF_PATTERN.
    Returns [] if content_blocks.json is absent or unreadable.
    """
    cb_path = paper_dir / "content_blocks.json"
    if not cb_path.is_file():
        return []
    try:
        blocks = json.loads(cb_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    seen: dict[str, None] = {}  # ordered dedupe
    for block in blocks[:_SCAN_BLOCKS]:
        if not isinstance(block, dict):
            continue
        text = block.get("text") or ""
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            if _AFF_PATTERN.search(line) and line not in seen:
                seen[line] = None
                if len(seen) >= _MAX_AFFS:
                    break
        if len(seen) >= _MAX_AFFS:
            break
    return list(seen)


def _ensure_institutions_registry(path: Path) -> dict:
    """Load registry from path if it exists; otherwise return a blank institutions registry."""
    if path.is_file():
        return load_registry(path)
    return {
        "schema_version": "0.1.0",
        "facets": [{"id": "institution"}],
        "entries": {},
    }


def resolve_institutions(
    raw_names: list[str],
    registry: dict,
    log_path: Path,
) -> list[str]:
    """Map raw institution name strings to registry IDs (deduped, order-preserving).

    - Hit  → use existing id; idempotently add the raw form as an alias.
    - Miss → create a new entry.
    Returns deduped list of IDs in input order.
    """
    seen: dict[str, None] = {}  # ordered dedupe
    for name in raw_names:
        name = name.strip()
        if not name:
            continue
        eid = find_by_surface(registry, "institution", name)
        if eid is not None:
            add_alias(registry, eid, name, "auto-stream", log_path)
        else:
            eid = create_entry(registry, "institution", name, "auto-stream", log_path)
        if eid not in seen:
            seen[eid] = None
    return list(seen)


def populate_authorship(
    library_dir: Path,
    institutions_dir: Path,
    fetch: Callable[[str], dict[str, Any] | None],
    progress: Callable[[str], None] = lambda m: None,
) -> dict[str, int]:
    """Populate authorship.json for each paper in library_dir.

    For each paper:
      1. Try fetch(doi) → OpenAlex record.
      2. On None/exception → PDF front-page fallback via content_blocks.json.
      3. If neither yields anything → failed.

    Saves registry once at end. Returns counters dict.
    """
    institutions_dir.mkdir(parents=True, exist_ok=True)
    registry_path = institutions_dir / "registry.json"
    log_path = institutions_dir / "registry_log.jsonl"
    registry = _ensure_institutions_registry(registry_path)

    paper_dirs = sorted(
        p.parent for p in library_dir.glob("*/literature_card.json")
    )

    populated = pdf_fallback = skipped_no_doi = failed = 0

    for i, paper_dir in enumerate(paper_dirs):
        if i > 0 and i % 10 == 0:
            progress(f"{i}/{len(paper_dirs)} processed")

        # --- resolve DOI ---
        card_path = paper_dir / "literature_card.json"
        try:
            card = json.loads(card_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            skipped_no_doi += 1
            continue

        doi = ((card.get("paper") or {}).get("doi") or "").strip()
        if not doi:
            skipped_no_doi += 1
            continue

        # --- try primary fetch ---
        rec: dict[str, Any] | None = None
        try:
            rec = fetch(doi)
        except Exception:  # noqa: BLE001
            rec = None

        # --- PDF fallback ---
        if rec is None:
            raw_affs = _pdf_fallback_affiliations(paper_dir)
            if raw_affs:
                rec = {
                    "authors": [],
                    "source": "pdf_front_page",
                    "_raw_affs": raw_affs,
                }
            else:
                failed += 1
                continue

        # --- build authorship doc ---
        paper_id = paper_dir.name
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if rec.get("source") == "pdf_front_page":
            raw_affs = rec.get("_raw_affs") or []
            institution_ids = resolve_institutions(raw_affs, registry, log_path)
            doc: dict[str, Any] = {
                "paper_id": paper_id,
                "authors": [],
                "source": "pdf_front_page",
                "fetched_at": now,
                "raw_affiliations": raw_affs,
                "institution_ids": institution_ids,
            }
            pdf_fallback += 1
        else:
            authors_out = []
            for author in rec.get("authors") or []:
                inst_ids = resolve_institutions(
                    author.get("raw_affiliations") or [], registry, log_path
                )
                authors_out.append({
                    "name": author.get("name", ""),
                    "position": author.get("position", 0),
                    "is_senior": author.get("is_senior", False),
                    "raw_affiliations": author.get("raw_affiliations") or [],
                    "institution_ids": inst_ids,
                })
            doc = {
                "paper_id": paper_id,
                "authors": authors_out,
                "source": rec.get("source", "unknown"),
                "fetched_at": now,
            }
            populated += 1

        # --- write output ---
        out_path = paper_dir / "authorship.json"
        out_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    save_registry(registry_path, registry)
    progress(
        f"done: {populated} populated, {pdf_fallback} pdf_fallback, "
        f"{skipped_no_doi} skipped_no_doi, {failed} failed"
    )
    return {
        "populated": populated,
        "pdf_fallback": pdf_fallback,
        "skipped_no_doi": skipped_no_doi,
        "failed": failed,
    }
