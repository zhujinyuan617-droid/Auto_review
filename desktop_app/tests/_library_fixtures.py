from __future__ import annotations

import json
from pathlib import Path


def write_card(library: Path, paper_id: str, *, title: str, year: str = "2020",
               journal: str = "Fuel", doi: str = "", tags: list[str] | None = None,
               findings: list[str] | None = None) -> None:
    """Write a minimal slim literature_card.json for one paper under library/<id>/."""
    paper_dir = library / paper_id
    paper_dir.mkdir(parents=True, exist_ok=True)
    card = {
        "schema_version": "0.2.0",
        "paper_id": paper_id,
        "paper": {"title": title, "doi": doi, "year": year, "journal": journal, "paper_type": "article"},
        "classification": {
            "research_objects": tags or [], "methods": [], "domain_tags": [],
            "gas_systems": [], "scale": [],
        },
        "summary": {"objective": f"Study {title}", "main_findings": findings or ["A finding."], "methods_systems": ""},
        "ai_warnings": [],
    }
    (paper_dir / "literature_card.json").write_text(json.dumps(card), encoding="utf-8")
