from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.io_utils import atomic_write_csv_dicts
from docdecomp.literature_card import ensure_card_defaults, load_json, validate_card
from docdecomp.slim_card import SLIM_SCHEMA_VERSION, ensure_slim_defaults, validate_slim_card

# v2 cards (schema_version 0.2.0) remain valid slim cards during the regen
# transition window and should be validated the same way as current slim cards
# (0.3.0).  Extend this set when new slim versions are introduced.
SLIM_SCHEMA_VERSIONS = {"0.2.0", "0.3.0"}


FIELDNAMES = [
    "paper_id",
    "schema_version",
    "status",
    "evidence_count",
    "unknown_reading_block_count",
    "bad_source_ref_count",
    "missing_evidence_count",
    "page_mismatch_count",
    "empty_required_text_count",
    "tag_count",
    "finding_count",
    "warnings",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated literature cards.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--paper-id", action="append", help="Validate one paper id. May be repeated.")
    parser.add_argument("--card-name", default="literature_card.json")
    parser.add_argument("--report", default=str(ROOT / "reports" / "literature_card_quality.csv"))
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    library_dir = Path(args.library_dir)
    paper_dirs = [library_dir / paper_id for paper_id in args.paper_id] if args.paper_id else sorted(
        path for path in library_dir.iterdir() if path.is_dir() and (path / args.card_name).exists()
    )

    rows = []
    for paper_dir in paper_dirs:
        card = load_json(paper_dir / args.card_name)
        reading = load_json(paper_dir / "reading_blocks.json")
        metadata = load_json(paper_dir / "metadata_candidates.json")
        if card.get("schema_version") in SLIM_SCHEMA_VERSIONS:
            actual_schema_version = card.get("schema_version", SLIM_SCHEMA_VERSION)
            card = ensure_slim_defaults(card, reading, metadata)
            validation = validate_slim_card(card)
            row = {
                "paper_id": card.get("paper_id") or reading.get("paper_id"),
                "schema_version": actual_schema_version,
                "status": "ok" if validation["status"] == "ok" else "fail",
                "evidence_count": 0,
                "unknown_reading_block_count": 0,
                "bad_source_ref_count": 0,
                "missing_evidence_count": 0,
                "page_mismatch_count": 0,
                "empty_required_text_count": 0,
                "tag_count": validation["n_tags"],
                "finding_count": validation["n_findings"],
                "warnings": "; ".join(validation["warnings"]),
            }
        else:
            card = ensure_card_defaults(card, reading, metadata)
            row = validate_card(card, reading)
            row["schema_version"] = card.get("schema_version", "")
            row["tag_count"] = ""
            row["finding_count"] = ""
        rows.append(row)

    report_path = Path(args.report)
    atomic_write_csv_dicts(report_path, FIELDNAMES, rows)
    print(f"Wrote {report_path}")
    for row in rows:
        print(
            f"{row['paper_id']}: {row['status']}; schema={row['schema_version']}; evidence={row['evidence_count']}; "
            f"unknown_rb={row['unknown_reading_block_count']}; bad_source={row['bad_source_ref_count']}; "
            f"missing_evidence={row['missing_evidence_count']}; page_mismatch={row['page_mismatch_count']}; "
            f"empty_text={row['empty_required_text_count']}; tags={row['tag_count']}; findings={row['finding_count']}"
        )
        if row["warnings"]:
            print(f"  warnings: {row['warnings']}")
    return 0 if all(row["status"] == "ok" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
