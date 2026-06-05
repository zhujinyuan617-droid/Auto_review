from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from paperpool.hash_utils import scan_pdf_hashes
from paperpool.io_utils import atomic_write_text, write_csv, write_json
from paperpool.pdf_probe import DECISION_CANDIDATE, DECISION_MANUAL, probe_pdf

DEFAULT_ZOTERO_STORAGE = Path.home() / "Zotero" / "storage"
DEFAULT_ZOTERO_DB = Path.home() / "Zotero" / "zotero.sqlite"
DEFAULT_POOL_DIR = PROJECT_ROOT / "paper"
DEFAULT_MANIFEST = PROJECT_ROOT / "state" / "zotero_import_manifest.json"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "zotero_import_report.csv"
DEFAULT_SUMMARY_REPORT = PROJECT_ROOT / "reports" / "zotero_import_summary.md"
DEFAULT_DB_SNAPSHOT_DIR = PROJECT_ROOT / "data" / "zotero_import" / "db_snapshots"

SCHEMA_VERSION = "0.2.0"
PARENT_OVERLOAD_THRESHOLD = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan Zotero PDFs, group by hash, compare against paper_pool, and write an intake report."
    )
    parser.add_argument("--zotero-storage", type=Path, default=DEFAULT_ZOTERO_STORAGE)
    parser.add_argument("--zotero-db", type=Path, default=DEFAULT_ZOTERO_DB)
    parser.add_argument("--pool-dir", type=Path, default=DEFAULT_POOL_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--summary-report", type=Path, default=DEFAULT_SUMMARY_REPORT)
    parser.add_argument("--db-snapshot-dir", type=Path, default=DEFAULT_DB_SNAPSHOT_DIR)
    parser.add_argument(
        "--db-mode",
        choices=["auto", "direct", "snapshot", "none"],
        default="auto",
        help="How to read zotero.sqlite. auto uses direct in dry-run and snapshot otherwise.",
    )
    parser.add_argument("--parent-overload-threshold", type=int, default=PARENT_OVERLOAD_THRESHOLD)
    parser.add_argument("--limit", type=int, default=None, help="Scan only the first N sorted Zotero PDFs.")
    parser.add_argument("--dry-run", action="store_true", help="Print summary without writing manifest/report.")
    return parser.parse_args()


def normalize_doi_suffix(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def filename_doi_key(value: str) -> str:
    stem = Path(value).stem.lower()
    match = re.search(
        r"(?:10[._-]1016[._-])?j[._-]([a-z0-9]+)[._-]((?:19|20)\d{2})[._-]([a-z0-9._-]+)$",
        stem,
    )
    if not match:
        return ""
    journal, year, suffix = match.groups()
    suffix_key = normalize_doi_suffix(suffix)
    return f"{journal}{year}{suffix_key}" if suffix_key else ""


def doi_key(value: str) -> str:
    lowered = str(value or "").lower()
    match = re.search(r"10\.1016/j\.([a-z0-9]+)\.((?:19|20)\d{2})\.([a-z0-9.]+)", lowered)
    if not match:
        return ""
    journal, year, suffix = match.groups()
    suffix_key = normalize_doi_suffix(suffix)
    return f"{journal}{year}{suffix_key}" if suffix_key else ""


def relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def join_values(values: list[Any]) -> str:
    return "; ".join(str(value) for value in values if str(value))


def unique_sorted(values: list[Any]) -> list[str]:
    return sorted({str(value) for value in values if str(value)})


def snapshot_zotero_db(db_path: Path, snapshot_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    target = snapshot_dir / f"zotero_{timestamp}.sqlite"
    temp_path = target.with_name(f".{target.name}.tmp-{os.getpid()}-{uuid4().hex}")
    try:
        shutil.copy2(db_path, temp_path)
        temp_path.replace(target)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return target


def connect_sqlite_readonly(path: Path) -> sqlite3.Connection:
    uri = "file:" + path.as_posix() + "?mode=ro&immutable=1"
    return sqlite3.connect(uri, uri=True)


def load_zotero_attachment_metadata(
    *,
    db_path: Path,
    db_mode: str,
    dry_run: bool,
    snapshot_dir: Path,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    summary: dict[str, Any] = {
        "db_mode": db_mode,
        "db_available": db_path.exists(),
        "db_path": str(db_path),
        "db_snapshot": "",
        "db_error": "",
        "pdf_attachment_records": 0,
        "pdf_attachment_records_missing_file": 0,
        "attachment_records_without_parent": 0,
        "parent_items_with_pdf": 0,
        "parent_items_with_multiple_pdf_records": 0,
        "largest_parent_pdf_record_count": 0,
    }
    if db_mode == "none" or not db_path.exists():
        return {}, summary

    source_path = db_path
    if db_mode == "snapshot" or (db_mode == "auto" and not dry_run):
        try:
            source_path = snapshot_zotero_db(db_path, snapshot_dir)
            summary["db_snapshot"] = str(source_path)
        except OSError as exc:
            summary["db_error"] = f"snapshot_failed:{exc}"
            source_path = db_path

    try:
        connection = connect_sqlite_readonly(source_path)
    except sqlite3.Error as exc:
        summary["db_error"] = f"connect_failed:{exc}"
        return {}, summary

    try:
        cursor = connection.cursor()
        fields = {row[1]: row[0] for row in cursor.execute("select fieldID, fieldName from fields")}

        def field_value(item_id: int | None, field_name: str) -> str:
            if not item_id:
                return ""
            field_id = fields.get(field_name)
            if field_id is None:
                return ""
            row = cursor.execute(
                """
                select v.value
                from itemData d join itemDataValues v on v.valueID = d.valueID
                where d.itemID=? and d.fieldID=?
                limit 1
                """,
                (item_id, field_id),
            ).fetchone()
            return str(row[0]) if row else ""

        rows = cursor.execute(
            """
            select ia.itemID, ia.parentItemID, ia.path, ia.contentType, child.key, parent.key
            from itemAttachments ia
            join items child on child.itemID = ia.itemID
            left join items parent on parent.itemID = ia.parentItemID
            where lower(coalesce(ia.path,'')) like '%.pdf%'
            order by child.key
            """
        ).fetchall()
        parent_counts = Counter(row[1] for row in rows if row[1])
        summary["pdf_attachment_records"] = len(rows)
        summary["attachment_records_without_parent"] = sum(1 for row in rows if not row[1])
        summary["parent_items_with_pdf"] = len(parent_counts)
        summary["parent_items_with_multiple_pdf_records"] = sum(1 for count in parent_counts.values() if count > 1)
        summary["largest_parent_pdf_record_count"] = max(parent_counts.values(), default=0)

        by_storage_key: dict[str, dict[str, Any]] = {}
        missing_records = 0
        for child_id, parent_id, path_value, content_type, child_key, parent_key in rows:
            file_name = str(path_value or "").removeprefix("storage:")
            attachment = {
                "child_item_id": child_id,
                "parent_item_id": parent_id,
                "child_key": str(child_key or ""),
                "parent_key": str(parent_key or ""),
                "attachment_path": str(path_value or ""),
                "attachment_filename": file_name,
                "content_type": str(content_type or ""),
                "parent_pdf_count": int(parent_counts.get(parent_id, 0)) if parent_id else 0,
                "parent_title": field_value(parent_id, "title"),
                "parent_doi": field_value(parent_id, "DOI"),
                "parent_date": field_value(parent_id, "date"),
                "parent_publication": field_value(parent_id, "publicationTitle"),
            }
            if not file_name:
                missing_records += 1
            by_storage_key[str(child_key or "")] = attachment
        summary["pdf_attachment_records_missing_file"] = missing_records
        return by_storage_key, summary
    except sqlite3.Error as exc:
        summary["db_error"] = f"query_failed:{exc}"
        return {}, summary
    finally:
        connection.close()


def classify_record(
    *,
    in_pool: bool,
    probe_decision: str,
) -> str:
    if in_pool:
        return "exact_duplicate_in_pool"
    if probe_decision in {"reject_broken_pdf", "reject_non_literature_body"}:
        return probe_decision
    if probe_decision == DECISION_CANDIDATE:
        return "candidate_for_pool"
    return DECISION_MANUAL


def build_import_report(
    *,
    zotero_paths: list[Path],
    pool_paths: list[Path],
    zotero_storage: Path,
    pool_dir: Path,
    parent_overload_threshold: int,
    db_metadata_by_storage_key: dict[str, dict[str, Any]],
    db_summary: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    zotero_hashes = scan_pdf_hashes(zotero_paths)
    pool_hashes = scan_pdf_hashes(pool_paths)

    records: list[dict[str, Any]] = []
    csv_rows: list[dict[str, Any]] = []
    for sha, paths in sorted(zotero_hashes.items(), key=lambda item: str(item[1][0]).lower()):
        sorted_paths = sorted(paths, key=lambda item: str(item).lower())
        representative = sorted_paths[0]
        storage_keys = unique_sorted([path.parent.name for path in sorted_paths])
        filenames = unique_sorted([path.name for path in sorted_paths])
        file_sizes = sorted({path.stat().st_size for path in sorted_paths})
        filename_keys = unique_sorted([filename_doi_key(path.name) for path in sorted_paths])
        db_items = [db_metadata_by_storage_key.get(path.parent.name, {}) for path in sorted_paths]
        parent_keys = unique_sorted([item.get("parent_key", "") for item in db_items])
        parent_dois = unique_sorted([item.get("parent_doi", "") for item in db_items])
        parent_titles = unique_sorted([item.get("parent_title", "") for item in db_items])
        parent_counts = sorted({int(item.get("parent_pdf_count") or 0) for item in db_items if item})
        overloaded_parent_keys = unique_sorted(
            [
                item.get("parent_key", "")
                for item in db_items
                if int(item.get("parent_pdf_count") or 0) > parent_overload_threshold
            ]
        )

        metadata_conflicts: list[str] = []
        for path in sorted_paths:
            attachment = db_metadata_by_storage_key.get(path.parent.name, {})
            fkey = filename_doi_key(path.name)
            pkey = doi_key(str(attachment.get("parent_doi") or ""))
            if fkey and pkey and fkey != pkey:
                metadata_conflicts.append(f"{path.parent.name}:{fkey}!={pkey}")

        pool_matches = sorted(pool_hashes.get(sha, []), key=lambda item: str(item).lower())
        in_pool = bool(pool_matches)
        has_internal_duplicates = len(sorted_paths) > 1
        parent_overloaded = bool(overloaded_parent_keys)
        metadata_conflict = bool(metadata_conflicts)
        representative_probe = probe_pdf(representative)
        probe_decision = str(representative_probe.get("pool_decision") or DECISION_MANUAL)
        status = classify_record(
            in_pool=in_pool,
            probe_decision=probe_decision,
        )
        warnings = list(representative_probe.get("warnings") or [])
        if has_internal_duplicates:
            warnings.append("zotero_internal_exact_duplicates")
        if parent_overloaded:
            warnings.append("parent_attachment_overload")
        if metadata_conflict:
            warnings.append("filename_parent_doi_conflict")
        if not filename_keys:
            warnings.append("no_filename_doi_key")

        candidate_id = f"ZOT-{sha[:12]}"
        record = {
            "candidate_id": candidate_id,
            "status": status,
            "sha256": sha,
            "is_new_to_pool": not in_pool,
            "probe_pool_decision": probe_decision,
            "document_class": representative_probe.get("document_class", "unknown"),
            "decision_reasons": representative_probe.get("decision_reasons") or [],
            "zotero_file_count": len(sorted_paths),
            "has_internal_duplicates": has_internal_duplicates,
            "representative_filename": representative.name,
            "representative_path": str(representative.resolve()),
            "zotero_paths": [str(path.resolve()) for path in sorted_paths],
            "zotero_storage_keys": storage_keys,
            "size_bytes": file_sizes[0] if file_sizes else 0,
            "size_bytes_values": file_sizes,
            "pool_match_paths": [str(path.resolve()) for path in pool_matches],
            "filename_doi_keys": filename_keys,
            "parent_overloaded": parent_overloaded,
            "overloaded_parent_keys": overloaded_parent_keys,
            "parent_keys": parent_keys,
            "parent_pdf_counts": parent_counts,
            "parent_dois": parent_dois,
            "parent_titles": parent_titles,
            "metadata_conflict": metadata_conflict,
            "metadata_conflicts": metadata_conflicts,
            "warnings": warnings,
            "pdf_probe": representative_probe,
        }
        records.append(record)
        csv_rows.append(
            {
                "candidate_id": candidate_id,
                "status": status,
                "sha256": sha,
                "is_new_to_pool": str(not in_pool).lower(),
                "probe_pool_decision": probe_decision,
                "document_class": representative_probe.get("document_class", "unknown"),
                "page_count": representative_probe.get("page_count", 0),
                "extracted_text_chars": representative_probe.get("extracted_text_chars", 0),
                "zotero_file_count": len(sorted_paths),
                "has_internal_duplicates": str(has_internal_duplicates).lower(),
                "parent_overloaded": str(parent_overloaded).lower(),
                "metadata_conflict": str(metadata_conflict).lower(),
                "representative_filename": representative.name,
                "size_bytes": file_sizes[0] if file_sizes else 0,
                "pool_match_count": len(pool_matches),
                "pool_match_paths": join_values([relative_or_absolute(path) for path in pool_matches]),
                "filename_doi_keys": join_values(filename_keys),
                "zotero_storage_keys": join_values(storage_keys),
                "zotero_paths": join_values([str(path.resolve()) for path in sorted_paths]),
                "parent_keys": join_values(parent_keys),
                "parent_pdf_counts": join_values(parent_counts),
                "parent_dois": join_values(parent_dois),
                "parent_titles": join_values([title[:240] for title in parent_titles]),
                "decision_reasons": join_values(representative_probe.get("decision_reasons") or []),
                "warnings": join_values(warnings),
            }
        )

    status_counts = Counter(record["status"] for record in records)
    document_class_counts = Counter(record["document_class"] for record in records)
    warning_counts = Counter(warning for record in records for warning in record["warnings"])
    overloaded_parent_hashes: dict[str, set[str]] = defaultdict(set)
    for record in records:
        for parent_key in record["overloaded_parent_keys"]:
            overloaded_parent_hashes[parent_key].add(record["sha256"])

    overloaded_parent_details: dict[str, dict[str, Any]] = {}
    for attachment in db_metadata_by_storage_key.values():
        parent_key = str(attachment.get("parent_key") or "")
        parent_pdf_count = int(attachment.get("parent_pdf_count") or 0)
        if not parent_key or parent_pdf_count <= parent_overload_threshold:
            continue
        detail = overloaded_parent_details.setdefault(
            parent_key,
            {
                "parent_key": parent_key,
                "db_pdf_attachment_records": parent_pdf_count,
                "unique_hashes_seen": 0,
                "parent_doi": str(attachment.get("parent_doi") or ""),
                "parent_title": str(attachment.get("parent_title") or ""),
            },
        )
        detail["db_pdf_attachment_records"] = max(
            int(detail["db_pdf_attachment_records"]),
            parent_pdf_count,
        )
    for parent_key, hashes in overloaded_parent_hashes.items():
        detail = overloaded_parent_details.setdefault(
            parent_key,
            {
                "parent_key": parent_key,
                "db_pdf_attachment_records": 0,
                "unique_hashes_seen": 0,
                "parent_doi": "",
                "parent_title": "",
            },
        )
        detail["unique_hashes_seen"] = len(hashes)

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "zotero_storage": str(zotero_storage),
        "pool_dir": str(pool_dir),
        "parent_overload_threshold": parent_overload_threshold,
        "zotero_pdf_files": len(zotero_paths),
        "paper_pool_pdf_files": len(pool_paths),
        "zotero_unique_hashes": len(zotero_hashes),
        "pool_unique_hashes": len(pool_hashes),
        "zotero_files_exactly_in_pool": sum(len(paths) for sha, paths in zotero_hashes.items() if sha in pool_hashes),
        "zotero_unique_hashes_exactly_in_pool": sum(1 for sha in zotero_hashes if sha in pool_hashes),
        "zotero_unique_hashes_not_in_pool": sum(1 for sha in zotero_hashes if sha not in pool_hashes),
        "pool_unique_hashes_not_in_zotero": sum(1 for sha in pool_hashes if sha not in zotero_hashes),
        "zotero_internal_exact_duplicate_groups": sum(1 for paths in zotero_hashes.values() if len(paths) > 1),
        "zotero_internal_exact_duplicate_files": sum(len(paths) for paths in zotero_hashes.values() if len(paths) > 1),
        "status_counts": dict(sorted(status_counts.items())),
        "document_class_counts": dict(sorted(document_class_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "parent_overloaded_unique_hashes": sum(1 for record in records if record["parent_overloaded"]),
        "metadata_conflict_unique_hashes": sum(1 for record in records if record["metadata_conflict"]),
        "overloaded_parent_items": sorted(
            overloaded_parent_details.values(),
            key=lambda item: (-int(item["db_pdf_attachment_records"]), item["parent_key"]),
        ),
        "zotero_db": db_summary,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": summary["generated_at"],
        "summary": summary,
        "records": records,
    }
    return manifest, csv_rows, records


def print_summary(summary: dict[str, Any]) -> None:
    print("Zotero PDF scan summary")
    for key in [
        "zotero_pdf_files",
        "paper_pool_pdf_files",
        "zotero_unique_hashes",
        "zotero_unique_hashes_exactly_in_pool",
        "zotero_unique_hashes_not_in_pool",
        "pool_unique_hashes_not_in_zotero",
        "zotero_internal_exact_duplicate_groups",
        "zotero_internal_exact_duplicate_files",
    ]:
        print(f"{key}: {summary.get(key)}")
    print("status_counts:")
    for key, value in (summary.get("status_counts") or {}).items():
        print(f"  {key}: {value}")
    document_class_counts = summary.get("document_class_counts") or {}
    if document_class_counts:
        print("document_class_counts:")
        for key, value in document_class_counts.items():
            print(f"  {key}: {value}")
    warning_counts = summary.get("warning_counts") or {}
    if warning_counts:
        print("warning_counts:")
        for key, value in warning_counts.items():
            print(f"  {key}: {value}")
    overloaded_parent_items = summary.get("overloaded_parent_items") or []
    if overloaded_parent_items:
        print("overloaded_parent_items:")
        for item in overloaded_parent_items[:10]:
            print(
                "  "
                f"{item.get('parent_key')}: "
                f"db_pdf_attachment_records={item.get('db_pdf_attachment_records')}, "
                f"unique_hashes_seen={item.get('unique_hashes_seen')}"
            )
    db_summary = summary.get("zotero_db") or {}
    if db_summary.get("db_error"):
        print(f"zotero_db_error: {db_summary['db_error']}")
    elif db_summary.get("db_available"):
        print(
            "zotero_db: "
            f"attachments={db_summary.get('pdf_attachment_records')}, "
            f"parent_items_with_pdf={db_summary.get('parent_items_with_pdf')}, "
            f"largest_parent_pdf_record_count={db_summary.get('largest_parent_pdf_record_count')}"
        )


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Zotero Import Summary",
        "",
        f"Generated at: {summary.get('generated_at')}",
        f"Zotero storage: `{summary.get('zotero_storage')}`",
        f"Pool dir: `{summary.get('pool_dir')}`",
        "",
        "## Counts",
        "",
        f"- Zotero PDF files: {summary.get('zotero_pdf_files')}",
        f"- Zotero unique hashes: {summary.get('zotero_unique_hashes')}",
        f"- Paper pool PDF files: {summary.get('paper_pool_pdf_files')}",
        f"- Pool unique hashes: {summary.get('pool_unique_hashes')}",
        f"- Zotero unique hashes already in pool: {summary.get('zotero_unique_hashes_exactly_in_pool')}",
        f"- Zotero unique hashes not in pool: {summary.get('zotero_unique_hashes_not_in_pool')}",
        f"- Pool unique hashes not in Zotero: {summary.get('pool_unique_hashes_not_in_zotero')}",
        f"- Zotero internal duplicate groups: {summary.get('zotero_internal_exact_duplicate_groups')}",
        f"- Zotero internal duplicate files: {summary.get('zotero_internal_exact_duplicate_files')}",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in (summary.get("status_counts") or {}).items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Warning Counts", ""])
    for key, value in (summary.get("warning_counts") or {}).items():
        lines.append(f"- {key}: {value}")

    lines.extend(["", "## Document Class Counts", ""])
    for key, value in (summary.get("document_class_counts") or {}).items():
        lines.append(f"- {key}: {value}")

    overloaded = summary.get("overloaded_parent_items") or []
    if overloaded:
        lines.extend(
            [
                "",
                "## Overloaded Parent Items",
                "",
                "| parent_key | db_pdf_attachment_records | unique_hashes_seen | parent_doi | parent_title |",
                "| --- | ---: | ---: | --- | --- |",
            ]
        )
        for item in overloaded[:20]:
            title = str(item.get("parent_title") or "").replace("|", "/")[:180]
            doi = str(item.get("parent_doi") or "").replace("|", "/")
            lines.append(
                "| "
                f"{item.get('parent_key')} | "
                f"{item.get('db_pdf_attachment_records')} | "
                f"{item.get('unique_hashes_seen')} | "
                f"{doi} | "
                f"{title} |"
            )

    db_summary = summary.get("zotero_db") or {}
    lines.extend(
        [
            "",
            "## Zotero DB",
            "",
            f"- DB mode: {db_summary.get('db_mode')}",
            f"- DB available: {db_summary.get('db_available')}",
            f"- PDF attachment records: {db_summary.get('pdf_attachment_records')}",
            f"- Parent items with PDF: {db_summary.get('parent_items_with_pdf')}",
            f"- Parent items with multiple PDF records: {db_summary.get('parent_items_with_multiple_pdf_records')}",
            f"- Largest parent PDF record count: {db_summary.get('largest_parent_pdf_record_count')}",
            f"- DB snapshot: `{db_summary.get('db_snapshot')}`",
        ]
    )
    if db_summary.get("db_error"):
        lines.append(f"- DB error: `{db_summary.get('db_error')}`")

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Treat `status` as the import decision bucket.",
            "- Treat `warnings` as independent risk signals. They can still apply to PDFs that are already in the pool.",
            "- Do not trust overloaded Zotero parent metadata when deciding title, DOI, or filename.",
            "- This layer does not judge research-topic relevance; it only checks whether a file looks like a literature-body PDF.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    if not args.zotero_storage.exists():
        print(f"Zotero storage not found: {args.zotero_storage}", file=sys.stderr)
        return 2
    if not args.pool_dir.exists():
        print(f"paper_pool directory not found: {args.pool_dir}", file=sys.stderr)
        return 2

    zotero_paths = sorted(args.zotero_storage.rglob("*.pdf"), key=lambda item: str(item).lower())
    if args.limit is not None:
        zotero_paths = zotero_paths[: args.limit]
    pool_paths = sorted(args.pool_dir.glob("*.pdf"), key=lambda item: str(item).lower())

    db_metadata_by_storage_key, db_summary = load_zotero_attachment_metadata(
        db_path=args.zotero_db,
        db_mode=args.db_mode,
        dry_run=args.dry_run,
        snapshot_dir=args.db_snapshot_dir,
    )
    manifest, csv_rows, _records = build_import_report(
        zotero_paths=zotero_paths,
        pool_paths=pool_paths,
        zotero_storage=args.zotero_storage,
        pool_dir=args.pool_dir,
        parent_overload_threshold=args.parent_overload_threshold,
        db_metadata_by_storage_key=db_metadata_by_storage_key,
        db_summary=db_summary,
    )

    if args.dry_run:
        print(f"[dry-run] Manifest: {args.manifest}")
        print(f"[dry-run] Report: {args.report}")
        print(f"[dry-run] Summary: {args.summary_report}")
    else:
        write_json(args.manifest, manifest)
        fieldnames = [
            "candidate_id",
            "status",
            "sha256",
            "is_new_to_pool",
            "probe_pool_decision",
            "document_class",
            "page_count",
            "extracted_text_chars",
            "zotero_file_count",
            "has_internal_duplicates",
            "parent_overloaded",
            "metadata_conflict",
            "representative_filename",
            "size_bytes",
            "pool_match_count",
            "pool_match_paths",
            "filename_doi_keys",
            "zotero_storage_keys",
            "zotero_paths",
            "parent_keys",
            "parent_pdf_counts",
            "parent_dois",
            "parent_titles",
            "decision_reasons",
            "warnings",
        ]
        write_csv(args.report, csv_rows, fieldnames)
        atomic_write_text(args.summary_report, render_summary_markdown(manifest["summary"]))
        print(f"Manifest: {args.manifest}")
        print(f"Report: {args.report}")
        print(f"Summary: {args.summary_report}")

    print_summary(manifest["summary"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
