from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.io_utils import atomic_write_csv_dicts
from docdecomp.library_index import write_library_index
from docdecomp.package_builder import build_clean_package


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build clean literature packages from Docling JSON.")
    parser.add_argument("--json-dir", default=str(ROOT / "data" / "docling" / "json"))
    parser.add_argument("--md-dir", default=str(ROOT / "data" / "docling" / "md"))
    parser.add_argument("--pdf-dir", action="append", default=[], help="Directory or PDF file used to copy source.pdf into each paper package. May be repeated.")
    parser.add_argument("--output-dir", default=str(ROOT / "library"))
    parser.add_argument("--report", default=str(ROOT / "reports" / "clean_package_report.csv"))
    parser.add_argument("--paper-id", action="append", help="Build one paper id. May be repeated.")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    json_dir = Path(args.json_dir)
    md_dir = Path(args.md_dir)
    pdf_dirs = [Path(path) for path in args.pdf_dir]
    output_dir = Path(args.output_dir)
    report_path = Path(args.report)

    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    json_files = sorted(p for p in json_dir.glob("*.json") if p.is_file())
    if args.paper_id:
        wanted = set(args.paper_id)
        json_files = [path for path in json_files if path.stem.split("_", 1)[0] in wanted]
    if args.limit is not None:
        json_files = json_files[: args.limit]

    rows = []
    for json_path in json_files:
        md_path = md_dir / f"{json_path.stem}.md"
        result = build_clean_package(
            json_path=json_path,
            md_path=md_path if md_path.exists() else None,
            output_root=output_dir,
            pdf_dirs=pdf_dirs,
        )
        rows.append(
            {
                "paper_id": result.paper_id,
                "output_dir": str(result.output_dir),
                "content_blocks": result.content_blocks,
                "evidence_items": result.evidence_items,
                "figures": result.figures,
                "tables": result.tables,
                "text_blocks": result.text_blocks,
                "source_pdf_status": result.source_pdf_status,
                "source_pdf_path": result.source_pdf_path or "",
            }
        )
        print(
            f"{result.paper_id}: content_blocks={result.content_blocks}, evidence={result.evidence_items}, "
            f"figures={result.figures}, tables={result.tables}, text_blocks={result.text_blocks}, "
            f"source_pdf={result.source_pdf_status}"
        )

    atomic_write_csv_dicts(
        report_path,
        [
            "paper_id",
            "output_dir",
            "content_blocks",
            "evidence_items",
            "figures",
            "tables",
            "text_blocks",
            "source_pdf_status",
            "source_pdf_path",
        ],
        rows,
    )
    index_rows = write_library_index(output_dir)
    print(f"Report: {report_path}")
    print(f"Library index: {output_dir / 'index.csv'} ({len(index_rows)} papers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
