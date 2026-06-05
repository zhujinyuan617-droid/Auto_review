from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from paperpool.hash_utils import scan_pdf_hashes, sha256_file
from paperpool.io_utils import atomic_write_text, write_csv, write_json
from paperpool.pdf_probe import probe_pdf


DEFAULT_POOL_DIR = PROJECT_ROOT / "paper"
DEFAULT_MANIFEST = PROJECT_ROOT / "state" / "pool_manifest.json"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "pool_audit_report.csv"
DEFAULT_SUMMARY_REPORT = PROJECT_ROOT / "reports" / "pool_audit_summary.md"
SCHEMA_VERSION = "0.1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the formal paper_pool PDF directory without modifying PDFs.")
    parser.add_argument("--pool-dir", type=Path, default=DEFAULT_POOL_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--summary-report", type=Path, default=DEFAULT_SUMMARY_REPORT)
    parser.add_argument("--limit", type=int, default=None, help="Probe only the first N sorted PDFs.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing manifest/report.")
    return parser.parse_args()


def relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def join_values(values: list[Any]) -> str:
    return "; ".join(str(value) for value in values if str(value))


def build_audit(pool_dir: Path, *, limit: int | None = None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pdf_paths = sorted(pool_dir.glob("*.pdf"), key=lambda item: str(item).lower())
    if limit is not None:
        pdf_paths = pdf_paths[:limit]

    hash_groups = scan_pdf_hashes(pdf_paths)
    hash_to_paths = {
        sha: sorted(paths, key=lambda item: str(item).lower())
        for sha, paths in hash_groups.items()
    }
    path_to_sha = {path.resolve(): sha for sha, paths in hash_to_paths.items() for path in paths}
    duplicate_hashes = {sha for sha, paths in hash_to_paths.items() if len(paths) > 1}

    records: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    decision_counts: Counter[str] = Counter()
    document_class_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()

    for path in pdf_paths:
        resolved = path.resolve()
        sha = path_to_sha.get(resolved) or sha256_file(path)
        duplicate_paths = hash_to_paths.get(sha, [])
        probe = probe_pdf(path)
        pool_warnings = list(probe.get("warnings") or [])
        if sha in duplicate_hashes:
            pool_warnings.append("duplicate_hash_in_pool")
        warning_counts.update(pool_warnings)
        decision = str(probe.get("pool_decision") or "needs_manual_review")
        document_class = str(probe.get("document_class") or "unknown")
        decision_counts[decision] += 1
        document_class_counts[document_class] += 1

        record = {
            "sha256": sha,
            "path": str(resolved),
            "relative_path": relative_or_absolute(path),
            "filename": path.name,
            "duplicate_in_pool": sha in duplicate_hashes,
            "duplicate_pool_paths": [str(item.resolve()) for item in duplicate_paths],
            "pool_decision": decision,
            "document_class": document_class,
            "decision_reasons": probe.get("decision_reasons") or [],
            "warnings": pool_warnings,
            "probe": probe,
        }
        records.append(record)
        rows.append(
            {
                "sha256": sha,
                "pool_decision": decision,
                "document_class": document_class,
                "filename": path.name,
                "relative_path": relative_or_absolute(path),
                "size_bytes": probe.get("size_bytes", 0),
                "page_count": probe.get("page_count", 0),
                "extracted_text_chars": probe.get("extracted_text_chars", 0),
                "duplicate_in_pool": str(sha in duplicate_hashes).lower(),
                "duplicate_pool_paths": join_values([relative_or_absolute(item) for item in duplicate_paths]),
                "decision_reasons": join_values(probe.get("decision_reasons") or []),
                "warnings": join_values(pool_warnings),
                "parser_error": probe.get("parser_error", ""),
            }
        )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "pool_dir": str(pool_dir.resolve()),
        "pdf_files": len(pdf_paths),
        "unique_hashes": len(hash_groups),
        "duplicate_hash_groups": sum(1 for paths in hash_groups.values() if len(paths) > 1),
        "duplicate_pdf_files": sum(len(paths) for paths in hash_groups.values() if len(paths) > 1),
        "decision_counts": dict(sorted(decision_counts.items())),
        "document_class_counts": dict(sorted(document_class_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": summary["generated_at"],
        "summary": summary,
        "records": records,
    }
    return manifest, rows


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Pool Audit Summary",
        "",
        f"Generated at: {summary.get('generated_at')}",
        f"Pool dir: `{summary.get('pool_dir')}`",
        "",
        "## Counts",
        "",
        f"- PDF files: {summary.get('pdf_files')}",
        f"- Unique hashes: {summary.get('unique_hashes')}",
        f"- Duplicate hash groups: {summary.get('duplicate_hash_groups')}",
        f"- Duplicate PDF files: {summary.get('duplicate_pdf_files')}",
        "",
        "## Decision Counts",
        "",
    ]
    for key, value in (summary.get("decision_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Document Class Counts", ""])
    for key, value in (summary.get("document_class_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Warning Counts", ""])
    warning_counts = summary.get("warning_counts") or {}
    if warning_counts:
        for key, value in warning_counts.items():
            lines.append(f"- {key}: {value}")
    else:
        lines.append("- none: 0")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This audit does not delete, rename, or move PDFs.",
            "- `candidate_for_pool` means the file looks like a readable literature-body PDF.",
            "- `needs_manual_review` is intentionally conservative and does not mean the paper is unusable.",
            "",
        ]
    )
    return "\n".join(lines)


def print_summary(summary: dict[str, Any]) -> None:
    print("Pool audit summary")
    for key in ["pdf_files", "unique_hashes", "duplicate_hash_groups", "duplicate_pdf_files"]:
        print(f"{key}: {summary.get(key)}")
    print("decision_counts:")
    for key, value in (summary.get("decision_counts") or {}).items():
        print(f"  {key}: {value}")
    print("document_class_counts:")
    for key, value in (summary.get("document_class_counts") or {}).items():
        print(f"  {key}: {value}")
    warning_counts = summary.get("warning_counts") or {}
    if warning_counts:
        print("warning_counts:")
        for key, value in warning_counts.items():
            print(f"  {key}: {value}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    if not args.pool_dir.exists():
        print(f"Pool dir not found: {args.pool_dir}", file=sys.stderr)
        return 2

    manifest, rows = build_audit(args.pool_dir, limit=args.limit)
    if args.dry_run:
        print(f"[dry-run] Manifest: {args.manifest}")
        print(f"[dry-run] Report: {args.report}")
        print(f"[dry-run] Summary: {args.summary_report}")
    else:
        write_json(args.manifest, manifest)
        write_csv(
            args.report,
            rows,
            [
                "sha256",
                "pool_decision",
                "document_class",
                "filename",
                "relative_path",
                "size_bytes",
                "page_count",
                "extracted_text_chars",
                "duplicate_in_pool",
                "duplicate_pool_paths",
                "decision_reasons",
                "warnings",
                "parser_error",
            ],
        )
        atomic_write_text(args.summary_report, render_summary_markdown(manifest["summary"]))
        print(f"Manifest: {args.manifest}")
        print(f"Report: {args.report}")
        print(f"Summary: {args.summary_report}")

    print_summary(manifest["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
