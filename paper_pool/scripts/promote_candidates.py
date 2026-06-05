from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from paperpool.filename_normalizer import build_pool_filename, sanitize_filename
from paperpool.hash_utils import scan_pdf_hashes, sha256_file
from paperpool.io_utils import atomic_write_text, write_csv, write_json


DEFAULT_MANIFEST = PROJECT_ROOT / "state" / "zotero_import_manifest.json"
DEFAULT_POOL_DIR = PROJECT_ROOT / "paper"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "promotion_report.csv"
DEFAULT_PLAN = PROJECT_ROOT / "reports" / "promotion_plan.json"
DEFAULT_SUMMARY = PROJECT_ROOT / "reports" / "promotion_summary.md"
SCHEMA_VERSION = "0.1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote vetted Zotero candidates into paper_pool/paper.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--pool-dir", type=Path, default=DEFAULT_POOL_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument("--summary-report", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--candidate-id", action="append", default=[], help="Promote only this candidate id. Can repeat.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--include-manual-review", action="store_true")
    parser.add_argument("--on-conflict", choices=["error", "skip", "suffix"], default="suffix")
    parser.add_argument("--apply", action="store_true", help="Actually copy files. Without this, the script is dry-run.")
    return parser.parse_args()


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_or_absolute(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path.resolve())


def join_values(values: list[Any]) -> str:
    return "; ".join(str(value) for value in values if str(value))


def eligible_records(manifest: dict[str, Any], *, include_manual_review: bool, candidate_ids: set[str]) -> list[dict[str, Any]]:
    allowed_statuses = {"candidate_for_pool"}
    if include_manual_review:
        allowed_statuses.add("needs_manual_review")
    records = []
    for record in manifest.get("records") or []:
        if candidate_ids and record.get("candidate_id") not in candidate_ids:
            continue
        if not record.get("is_new_to_pool", False):
            continue
        if record.get("status") not in allowed_statuses:
            continue
        records.append(record)
    return records


def unique_target_path(pool_dir: Path, filename: str, sha: str, used_names: set[str], on_conflict: str) -> tuple[Path, str, list[str]]:
    reasons: list[str] = []
    candidate = pool_dir / filename
    normalized_key = candidate.name.lower()
    if normalized_key not in used_names and not candidate.exists():
        used_names.add(normalized_key)
        return candidate, "ready", reasons

    reasons.append("target_filename_conflict")
    if on_conflict == "error":
        return candidate, "error_conflict", reasons
    if on_conflict == "skip":
        return candidate, "skip_conflict", reasons

    stem = sanitize_filename(Path(filename).stem, max_chars=180)
    suffix = sha[:12]
    for index in range(1, 1000):
        extra = suffix if index == 1 else f"{suffix}_{index}"
        new_name = sanitize_filename(f"{stem}_{extra}.pdf", max_chars=220)
        candidate = pool_dir / new_name
        normalized_key = candidate.name.lower()
        if normalized_key not in used_names and not candidate.exists():
            used_names.add(normalized_key)
            reasons.append("target_filename_suffixed")
            return candidate, "ready", reasons
    return candidate, "error_conflict", reasons + ["unable_to_allocate_unique_filename"]


def build_plan(
    records: list[dict[str, Any]],
    pool_dir: Path,
    *,
    on_conflict: str,
    limit: int | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if limit is not None:
        records = records[:limit]

    pool_paths = sorted(pool_dir.glob("*.pdf"), key=lambda item: str(item).lower())
    pool_hashes = scan_pdf_hashes(pool_paths)
    used_names = {path.name.lower() for path in pool_paths}

    plan_rows: list[dict[str, Any]] = []
    action_counts: Counter[str] = Counter()
    for record in records:
        candidate_id = str(record.get("candidate_id") or "")
        sha = str(record.get("sha256") or "")
        source_path = Path(str(record.get("representative_path") or ""))
        reasons: list[str] = []

        if not source_path.exists():
            action = "skip_missing_source"
            target_path = pool_dir / build_pool_filename(record)
            reasons.append("source_missing")
        elif sha in pool_hashes:
            action = "skip_hash_already_in_pool"
            target_path = pool_hashes[sha][0]
            reasons.append("hash_already_in_pool")
        else:
            if sha256_file(source_path) != sha:
                action = "skip_source_hash_mismatch"
                target_path = pool_dir / build_pool_filename(record)
                reasons.append("source_hash_mismatch")
            else:
                filename = build_pool_filename(record)
                target_path, action, conflict_reasons = unique_target_path(pool_dir, filename, sha, used_names, on_conflict)
                reasons.extend(conflict_reasons)

        action_counts[action] += 1
        plan_rows.append(
            {
                "candidate_id": candidate_id,
                "action": action,
                "sha256": sha,
                "source_path": str(source_path.resolve()) if source_path.exists() else str(source_path),
                "target_path": str(target_path.resolve()),
                "target_filename": target_path.name,
                "status": record.get("status", ""),
                "document_class": record.get("document_class", ""),
                "representative_filename": record.get("representative_filename", ""),
                "warnings": record.get("warnings") or [],
                "reasons": reasons,
            }
        )

    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "mode": "plan",
        "pool_dir": str(pool_dir.resolve()),
        "selected_records": len(records),
        "action_counts": dict(sorted(action_counts.items())),
    }
    plan = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": summary["generated_at"],
        "summary": summary,
        "records": plan_rows,
    }
    return plan, plan_rows


def apply_plan(plan_rows: list[dict[str, Any]]) -> Counter[str]:
    result_counts: Counter[str] = Counter()
    for row in plan_rows:
        if row["action"] != "ready":
            result_counts[row["action"]] += 1
            row["apply_result"] = row["action"]
            continue
        source = Path(row["source_path"])
        target = Path(row["target_path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target.with_name(f".{target.name}.tmp-promote")
        try:
            if temp_path.exists():
                temp_path.unlink()
            shutil.copy2(source, temp_path)
            copied_sha = sha256_file(temp_path)
            if copied_sha != row["sha256"]:
                row["apply_result"] = "copied_hash_mismatch"
                result_counts["copied_hash_mismatch"] += 1
                temp_path.unlink(missing_ok=True)
                continue
            temp_path.replace(target)
            row["apply_result"] = "copied"
            result_counts["copied"] += 1
        finally:
            if temp_path.exists():
                temp_path.unlink()
    return result_counts


def render_summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Promotion Summary",
        "",
        f"Generated at: {summary.get('generated_at')}",
        f"Mode: {summary.get('mode')}",
        f"Pool dir: `{summary.get('pool_dir')}`",
        f"Selected records: {summary.get('selected_records')}",
        "",
        "## Action Counts",
        "",
    ]
    for key, value in (summary.get("action_counts") or {}).items():
        lines.append(f"- {key}: {value}")
    if summary.get("apply_result_counts"):
        lines.extend(["", "## Apply Result Counts", ""])
        for key, value in summary.get("apply_result_counts", {}).items():
            lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Without `--apply`, this is only a promotion plan.",
            "- Promotion copies files into `paper/`; it never deletes or edits Zotero files.",
            "- Run `py .\\scripts\\audit_pool.py` after an apply run.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(plan: dict[str, Any], rows: list[dict[str, Any]], *, report: Path, plan_path: Path, summary_report: Path) -> None:
    write_json(plan_path, plan)
    write_csv(
        report,
        [
            {
                **row,
                "warnings": join_values(row.get("warnings") or []),
                "reasons": join_values(row.get("reasons") or []),
            }
            for row in rows
        ],
        [
            "candidate_id",
            "action",
            "apply_result",
            "sha256",
            "source_path",
            "target_path",
            "target_filename",
            "status",
            "document_class",
            "representative_filename",
            "warnings",
            "reasons",
        ],
    )
    atomic_write_text(summary_report, render_summary_markdown(plan["summary"]))


def print_summary(summary: dict[str, Any]) -> None:
    print("Promotion summary")
    print(f"mode: {summary.get('mode')}")
    print(f"selected_records: {summary.get('selected_records')}")
    print("action_counts:")
    for key, value in (summary.get("action_counts") or {}).items():
        print(f"  {key}: {value}")
    if summary.get("apply_result_counts"):
        print("apply_result_counts:")
        for key, value in (summary.get("apply_result_counts") or {}).items():
            print(f"  {key}: {value}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 2
    if not args.pool_dir.exists():
        print(f"Pool dir not found: {args.pool_dir}", file=sys.stderr)
        return 2

    manifest = load_manifest(args.manifest)
    records = eligible_records(
        manifest,
        include_manual_review=args.include_manual_review,
        candidate_ids=set(args.candidate_id),
    )
    plan, rows = build_plan(records, args.pool_dir, on_conflict=args.on_conflict, limit=args.limit)
    plan["summary"]["mode"] = "apply" if args.apply else "dry-run"

    if args.apply:
        result_counts = apply_plan(rows)
        plan["summary"]["apply_result_counts"] = dict(sorted(result_counts.items()))
    else:
        for row in rows:
            row["apply_result"] = ""

    write_outputs(plan, rows, report=args.report, plan_path=args.plan, summary_report=args.summary_report)
    print(f"Plan: {args.plan}")
    print(f"Report: {args.report}")
    print(f"Summary: {args.summary_report}")
    print_summary(plan["summary"])

    if any(row["action"].startswith("error") for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
