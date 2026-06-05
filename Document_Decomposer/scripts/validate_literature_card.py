from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.literature_card import ensure_card_defaults, load_json, validate_card, write_validation_report


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
        card = ensure_card_defaults(card, reading, metadata)
        row = validate_card(card, reading)
        rows.append(row)

    report_path = Path(args.report)
    write_validation_report(report_path, rows)
    print(f"Wrote {report_path}")
    for row in rows:
        print(
            f"{row['paper_id']}: {row['status']}; evidence={row['evidence_count']}; "
            f"unknown_rb={row['unknown_reading_block_count']}; bad_source={row['bad_source_ref_count']}; "
            f"missing_evidence={row['missing_evidence_count']}; page_mismatch={row['page_mismatch_count']}; "
            f"empty_text={row['empty_required_text_count']}"
        )
        if row["warnings"]:
            print(f"  warnings: {row['warnings']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
