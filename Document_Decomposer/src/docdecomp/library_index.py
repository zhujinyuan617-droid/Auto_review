from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import atomic_write_csv_dicts, write_json


SCHEMA_VERSION = "0.1.0"


def load_json_if_exists(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def index_row_for_paper(paper_dir: Path) -> dict[str, Any]:
    paper_id = paper_dir.name
    metadata = load_json_if_exists(paper_dir / "metadata_candidates.json")
    source_pdf = load_json_if_exists(paper_dir / "source_pdf.json")
    content = load_json_if_exists(paper_dir / "content_blocks.json")
    evidence = load_json_if_exists(paper_dir / "evidence.json")
    reading = load_json_if_exists(paper_dir / "reading_blocks.json")
    card = load_json_if_exists(paper_dir / "literature_card.json")
    candidates = metadata.get("metadata_candidates") or {}
    blocks = content.get("blocks") or []
    evidence_items = evidence.get("items") or []
    reading_blocks = reading.get("reading_blocks") or []

    return {
        "paper_id": paper_id,
        "package_dir": paper_id,
        "title": candidates.get("title", ""),
        "year": candidates.get("year", ""),
        "journal": candidates.get("journal", ""),
        "doi": candidates.get("doi", ""),
        "docling_name": candidates.get("docling_name", ""),
        "source_pdf": source_pdf.get("copied_path", "source.pdf" if (paper_dir / "source.pdf").exists() else ""),
        "source_pdf_status": source_pdf.get("status", ""),
        "original_filename": source_pdf.get("original_filename") or source_pdf.get("docling_origin_filename", ""),
        "original_path": source_pdf.get("original_path", ""),
        "sha256": source_pdf.get("sha256", ""),
        "content_blocks": len(blocks),
        "evidence_items": len(evidence_items),
        "figures": sum(1 for item in evidence_items if item.get("type") == "figure"),
        "tables": sum(1 for item in evidence_items if item.get("type") == "table"),
        "reading_blocks": len(reading_blocks),
        "has_ai_sections": (paper_dir / "ai_sections.json").exists(),
        "has_reading_blocks": bool(reading_blocks),
        "has_literature_card": bool(card),
    }


def build_library_index(library_dir: Path) -> list[dict[str, Any]]:
    paper_dirs = sorted(
        path
        for path in library_dir.iterdir()
        if path.is_dir() and (path / "content_blocks.json").exists()
    )
    return [index_row_for_paper(path) for path in paper_dirs]


def write_library_index(library_dir: Path) -> list[dict[str, Any]]:
    rows = build_library_index(library_dir)
    csv_fields = [
        "paper_id",
        "package_dir",
        "title",
        "year",
        "journal",
        "doi",
        "docling_name",
        "source_pdf",
        "source_pdf_status",
        "original_filename",
        "original_path",
        "sha256",
        "content_blocks",
        "evidence_items",
        "figures",
        "tables",
        "reading_blocks",
        "has_ai_sections",
        "has_reading_blocks",
        "has_literature_card",
    ]
    atomic_write_csv_dicts(library_dir / "index.csv", csv_fields, rows)
    write_json(
        library_dir / "index.json",
        {
            "schema_version": SCHEMA_VERSION,
            "library_dir": str(library_dir),
            "papers": rows,
        },
    )
    return rows
