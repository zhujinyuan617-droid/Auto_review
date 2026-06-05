from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.evidence_synthesis import (
    ensure_paper_syntheses_defaults,
    load_json,
    validate_paper_syntheses,
    write_paper_syntheses_report,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate generated article-internal syntheses.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--paper-id", action="append", help="Validate one paper id. May be repeated.")
    parser.add_argument("--atoms-name", default="evidence_atoms.json")
    parser.add_argument("--syntheses-name", default="paper_syntheses.json")
    parser.add_argument("--report", default=str(ROOT / "reports" / "paper_syntheses_quality.csv"))
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    library_dir = Path(args.library_dir)
    paper_dirs = [library_dir / paper_id for paper_id in args.paper_id] if args.paper_id else sorted(
        path for path in library_dir.iterdir() if path.is_dir() and (path / args.syntheses_name).exists()
    )

    rows = []
    for paper_dir in paper_dirs:
        package = load_json(paper_dir / args.syntheses_name)
        evidence_atoms = load_json(paper_dir / args.atoms_name)
        package = ensure_paper_syntheses_defaults(package, evidence_atoms)
        rows.append(validate_paper_syntheses(package, evidence_atoms))

    report_path = Path(args.report)
    write_paper_syntheses_report(report_path, rows)
    print(f"Wrote {report_path}")
    for row in rows:
        print(
            f"{row['paper_id']}: {row['status']}; syntheses={row['synthesis_count']}; "
            f"unknown_atom={row['unknown_evidence_atom_count']}; weak_support={row['weak_support_count']}; "
            f"duplicate_support={row['duplicate_support_count']}; "
            f"unsupported_scope={row['unsupported_scope_value_count']}; "
            f"empty_text={row['empty_required_text_count']}"
        )
        if row["warnings"]:
            print(f"  warnings: {row['warnings']}")
    return 0 if all(row["status"] == "ok" for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
