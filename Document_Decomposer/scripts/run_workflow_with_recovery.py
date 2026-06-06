from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.io_utils import atomic_write_text, write_json
from docdecomp.paper_profile import CONTENT_CJK_DEFER_THRESHOLD


CORE_OUTPUTS = {
    "reading": "reading_blocks.json",
    "card": "literature_card.json",
    "evidence_atoms": "evidence_atoms.json",
    "paper_syntheses": "paper_syntheses.json",
}
STAGE_ORDER = ["clean", "sections", "reading", "card", "evidence_atoms", "paper_syntheses"]


def safe_console() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name)
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            try:
                stream.reconfigure(errors="replace")
            except Exception:
                pass


def command_text(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def run_command(command: list[str], log_path: Path, dry_run: bool = False) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"$ {command_text(command)}\n\n"
    print(command_text(command))
    if dry_run:
        atomic_write_text(log_path, header + "[dry-run]\n")
        return 0
    completed = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    output = header
    if completed.stdout:
        output += completed.stdout
    if completed.stderr:
        output += "\n[stderr]\n" + completed.stderr
    atomic_write_text(log_path, output)
    return completed.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full library workflow with deterministic recovery passes."
    )
    parser.add_argument("--all", action="store_true", help="Process all active mainline papers.")
    parser.add_argument("--paper-id", action="append", help="Paper id to process. May be repeated.")
    parser.add_argument("--config", default=None, help="Path to ai.local.json for AI stages.")
    parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--json-dir", default=str(ROOT / "data" / "docling" / "json"))
    parser.add_argument("--md-dir", default=str(ROOT / "data" / "docling" / "md"))
    parser.add_argument("--staging-dir", default=str(ROOT / "data" / "ingest" / "pdfs"))
    parser.add_argument("--manifest", default=str(ROOT / "data" / "ingest" / "paper_manifest.json"))
    parser.add_argument(
        "--known-docling-file",
        default=str(ROOT / "config" / "docling_unresolved.json"),
        help="Persistent list of known bad PDFs to mark and skip on future all-runs.",
    )
    parser.add_argument(
        "--known-docling-id",
        action="append",
        default=[],
        help="Known bad PDF paper id to mark and skip. May be repeated.",
    )
    parser.add_argument("--parallel", type=int, default=6)
    parser.add_argument("--docling-parallel", type=int, default=2)
    parser.add_argument("--max-recovery-passes", type=int, default=1)
    parser.add_argument(
        "--retry-docling-once",
        action="store_true",
        help="Optionally retry Docling failures once at serial/low concurrency. Defaults to marking them unresolved.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def latest_pipeline_dir(output: str) -> Path | None:
    matches = re.findall(r"Run directory:\s*(.+)", output)
    if not matches:
        return None
    value = matches[-1].strip()
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def latest_from_downloads_dir(output: str) -> Path | None:
    matches = re.findall(r"Run directory:\s*(.+)", output)
    if not matches:
        return None
    value = matches[-1].strip()
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def selected_papers_from_log(text: str) -> list[str]:
    match = re.search(r"^Selected papers:\s*(.+)$", text, re.MULTILINE)
    if not match:
        return []
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def docling_failures_from_log(text: str) -> list[str]:
    match = re.search(r"Docling failed for:\s*(.+?)\.\s*Skipping", text)
    if not match:
        return []
    return [item.strip() for item in match.group(1).split(",") if item.strip()]


def classify_docling_failure(log_path: Path) -> str:
    text = read_text(log_path).lower()
    if "std::bad_alloc" in text or "bad_alloc" in text:
        return "docling_bad_alloc"
    if "failed to convert" in text:
        return "docling_failed_to_convert"
    if not text:
        return "docling_log_missing"
    return "docling_no_output"


def pipeline_failures(pipeline_dir: Path | None) -> list[dict[str, str]]:
    if not pipeline_dir:
        return []
    summary = pipeline_dir / "pipeline_summary.csv"
    if not summary.exists():
        return []
    rows = list(csv.DictReader(summary.open(encoding="utf-8-sig")))
    failures: list[dict[str, str]] = []
    for row in rows:
        status = row.get("status", "")
        paper_id = row.get("paper_id", "")
        stage = row.get("stage", "")
        if status.startswith("failed") and paper_id != "*":
            failures.append(
                {
                    "paper_id": paper_id,
                    "stage": stage,
                    "status": status,
                    "kind": f"pipeline_{stage}_failed",
                    "log_path": row.get("log_path", ""),
                }
            )
        elif stage == "language_gate" and status.startswith("deferred"):
            failures.append(
                {
                    "paper_id": paper_id,
                    "stage": stage,
                    "status": status,
                    "kind": "language_deferred",
                    "log_path": row.get("log_path", ""),
                }
            )
    return failures


def missing_core_outputs(paper_ids: list[str], library_dir: Path, excluded: set[str]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    for paper_id in paper_ids:
        if paper_id in excluded:
            continue
        paper_dir = library_dir / paper_id
        for stage, filename in CORE_OUTPUTS.items():
            if not (paper_dir / filename).exists():
                missing.append(
                    {
                        "paper_id": paper_id,
                        "stage": stage,
                        "status": "missing_output",
                        "kind": f"missing_{stage}",
                        "log_path": "",
                    }
                )
    return missing


def load_known_docling_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    if isinstance(data, list):
        return {str(item).upper() for item in data if str(item).strip()}
    if isinstance(data, dict):
        values = data.get("docling_unresolved") or data.get("paper_ids") or []
        return {str(item).upper() for item in values if str(item).strip()}
    return set()


def save_known_docling_ids(path: Path, paper_ids: set[str]) -> None:
    write_json(path, {"docling_unresolved": sorted(paper_ids)})


def build_main_command(
    args: argparse.Namespace,
    *,
    paper_ids: list[str] | None = None,
    force_dry_run: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_from_paper_downloads.py"),
        "--manifest",
        str(Path(args.manifest)),
        "--staging-dir",
        str(Path(args.staging_dir)),
        "--json-dir",
        str(Path(args.json_dir)),
        "--md-dir",
        str(Path(args.md_dir)),
        "--library-dir",
        str(Path(args.library_dir)),
        "--reports-dir",
        str(Path(args.reports_dir)),
        "--parallel",
        str(args.parallel),
        "--docling-parallel",
        str(args.docling_parallel),
        "--resume",
    ]
    if paper_ids is None and args.all:
        command.append("--all")
    for paper_id in paper_ids if paper_ids is not None else args.paper_id or []:
        command.extend(["--paper-id", paper_id])
    if args.config:
        command.extend(["--config", str(Path(args.config))])
    if args.dry_run or force_dry_run:
        command.append("--dry-run")
    return command


def retry_docling(paper_ids: list[str], args: argparse.Namespace, run_dir: Path, pass_index: int) -> int:
    if not paper_ids:
        return 0
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_from_paper_downloads.py"),
        "--manifest",
        str(Path(args.manifest)),
        "--staging-dir",
        str(Path(args.staging_dir)),
        "--json-dir",
        str(Path(args.json_dir)),
        "--md-dir",
        str(Path(args.md_dir)),
        "--library-dir",
        str(Path(args.library_dir)),
        "--reports-dir",
        str(Path(args.reports_dir)),
        "--skip-ingest",
        "--skip-pipeline",
        "--docling-parallel",
        "1",
    ]
    for paper_id in paper_ids:
        command.extend(["--paper-id", paper_id])
    if args.dry_run:
        command.append("--dry-run")
    return run_command(command, run_dir / "logs" / f"recovery_pass_{pass_index}_docling.log", args.dry_run)


def retry_pipeline_stages(failures: list[dict[str, str]], args: argparse.Namespace, run_dir: Path, pass_index: int) -> int:
    by_stage: dict[str, list[str]] = defaultdict(list)
    for failure in failures:
        stage = failure.get("stage", "")
        paper_id = failure.get("paper_id", "")
        if stage in STAGE_ORDER and paper_id:
            by_stage[stage].append(paper_id)

    exit_code = 0
    for stage in STAGE_ORDER:
        paper_ids = sorted(set(by_stage.get(stage, [])))
        if not paper_ids:
            continue
        command = [
            sys.executable,
            str(ROOT / "scripts" / "run_pipeline.py"),
            "--stage",
            stage,
            "--library-dir",
            str(Path(args.library_dir)),
            "--reports-dir",
            str(Path(args.reports_dir)),
            "--json-dir",
            str(Path(args.json_dir)),
            "--md-dir",
            str(Path(args.md_dir)),
            "--parallel",
            str(max(1, min(args.parallel, len(paper_ids)))),
            "--pdf-dir",
            str(Path(args.staging_dir)),
            "--pdf-dir",
            str(ROOT.parent / "paper_pool" / "paper"),
            "--force",
        ]
        for paper_id in paper_ids:
            command.extend(["--paper-id", paper_id])
        if args.config:
            command.extend(["--config", str(Path(args.config))])
        if args.dry_run:
            command.append("--dry-run")
        code = run_command(command, run_dir / "logs" / f"recovery_pass_{pass_index}_{stage}.log", args.dry_run)
        exit_code = exit_code or code
    return exit_code


def validate_core(paper_ids: list[str], excluded: set[str], args: argparse.Namespace, run_dir: Path) -> int:
    validation_ids = [paper_id for paper_id in paper_ids if paper_id not in excluded]
    if not validation_ids:
        return 0
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_pipeline.py"),
        "--stage",
        "validate",
        "--library-dir",
        str(Path(args.library_dir)),
        "--reports-dir",
        str(Path(args.reports_dir)),
    ]
    for paper_id in validation_ids:
        command.extend(["--paper-id", paper_id])
    if args.dry_run:
        command.append("--dry-run")
    return run_command(command, run_dir / "logs" / "final_validate.log", args.dry_run)


def write_markdown_report(run_dir: Path, report: dict) -> None:
    language_deferred = report.get("language_deferred") or []
    docling_unresolved = report.get("docling_unresolved") or []
    final_missing = report.get("final_missing_outputs") or []
    recovery_actions = report.get("recovery_actions") or []
    available_count = (
        report.get("selected_count", 0)
        - len(language_deferred)
        - len(docling_unresolved)
        - len({item.get("paper_id") for item in final_missing if item.get("paper_id")})
    )
    available_label = "Planned runnable papers" if report.get("mode") == "dry_run" else "Completed core papers"
    lines = [
        "# Workflow Final Report",
        "",
        f"- Mode: {report.get('mode', '')}",
        f"- Selected mainline papers: {report.get('selected_count', 0)}",
        f"- {available_label}: {max(0, available_count)}",
        f"- Language/content deferred: {len(language_deferred)}",
        f"- Docling unresolved: {len(docling_unresolved)}",
        f"- Missing core outputs: {len(final_missing)}",
        f"- Validation exit code: {report.get('validation_exit_code', '')}",
        "",
        "## Docling Unresolved",
        "",
    ]
    if docling_unresolved:
        by_id = {item.get("paper_id"): item for item in report.get("recovery_queue", []) if item.get("stage") == "docling"}
        for paper_id in docling_unresolved:
            item = by_id.get(paper_id, {})
            kind = item.get("kind", "docling_failed")
            lines.append(f"- {paper_id}: {kind}")
    else:
        lines.append("- none")
    lines.extend(["", "## Language Deferred", ""])
    if language_deferred:
        for paper_id in language_deferred:
            lines.append(f"- {paper_id}")
    else:
        lines.append("- none")
    lines.extend(["", "## Recovery Actions", ""])
    if recovery_actions:
        for action in recovery_actions:
            lines.append(f"- pass {action.get('pass')}: {action.get('action')} (code={action.get('code')})")
    else:
        lines.append("- none")
    lines.extend(["", "## Notes", ""])
    lines.append("- Docling failures are marked and excluded by default; the workflow does not spend time trying to rescue every bad PDF.")
    lines.append("- AI-generated paper content is only produced by the stage scripts; this runner does not hand-edit generated JSON content.")
    atomic_write_text(run_dir / "final_report.md", "\n".join(lines) + "\n")


def write_report(run_dir: Path, report: dict) -> None:
    write_json(run_dir / "final_report.json", report)
    write_json(run_dir / "recovery_queue.json", report.get("recovery_queue", []))
    write_markdown_report(run_dir, report)
    print(f"Recovery report: {run_dir / 'final_report.json'}")
    print(f"Markdown report: {run_dir / 'final_report.md'}")


def main() -> int:
    safe_console()
    args = parse_args()
    if not args.all and not args.paper_id:
        print("Use --all or --paper-id.")
        return 2

    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid4().hex[:8]}"
    run_dir = Path(args.reports_dir) / f"workflow_recovery_{run_id}"
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    known_docling_file = Path(args.known_docling_file)
    known_docling_ids = load_known_docling_ids(known_docling_file)
    known_docling_ids.update(str(paper_id).upper() for paper_id in args.known_docling_id)

    selection_log = run_dir / "logs" / "selection_plan.log"
    run_command(build_main_command(args, force_dry_run=True), selection_log, dry_run=False)
    planned_selected = selected_papers_from_log(read_text(selection_log))
    selected_for_run = [
        paper_id for paper_id in planned_selected if paper_id.upper() not in known_docling_ids
    ]
    known_selected = [
        paper_id for paper_id in planned_selected if paper_id.upper() in known_docling_ids
    ]

    main_log = run_dir / "logs" / "main_run.log"
    main_code = run_command(
        build_main_command(args, paper_ids=selected_for_run if args.all else None),
        main_log,
        args.dry_run,
    )
    if args.dry_run:
        report = {
            "run_dir": str(run_dir),
            "mode": "dry_run",
            "main_exit_code": main_code,
            "message": "Plan only. No Docling, AI, pipeline, recovery, or validation work was executed.",
            "selected_count": len(planned_selected),
            "selected_papers": planned_selected,
            "language_deferred": [],
            "docling_unresolved": sorted(known_selected),
            "final_missing_outputs": [],
            "validation_exit_code": "",
            "recovery_actions": [],
            "recovery_queue": [],
            "known_docling_file": str(known_docling_file),
        }
        write_report(run_dir, report)
        print("Workflow dry-run plan written.")
        return 0

    main_text = read_text(main_log)
    selected = planned_selected or selected_papers_from_log(main_text)
    docling_failed = docling_failures_from_log(main_text)
    from_downloads_dir = latest_from_downloads_dir(main_text)
    pipeline_dir = None
    if from_downloads_dir:
        pipeline_text = read_text(from_downloads_dir / "logs" / "pipeline.log")
        pipeline_dir = latest_pipeline_dir(pipeline_text)

    recovery_queue: list[dict[str, str]] = []
    for paper_id in known_selected:
        recovery_queue.append(
            {
                "paper_id": paper_id,
                "stage": "docling",
                "status": "known_unresolved",
                "kind": "docling_known_unresolved",
                "log_path": "",
            }
        )
    for paper_id in docling_failed:
        log_path = from_downloads_dir / "logs" / f"{paper_id}_docling.log" if from_downloads_dir else Path()
        recovery_queue.append(
            {
                "paper_id": paper_id,
                "stage": "docling",
                "status": "failed",
                "kind": classify_docling_failure(log_path),
                "log_path": str(log_path) if log_path else "",
            }
        )
    if docling_failed:
        known_docling_ids.update(paper_id.upper() for paper_id in docling_failed)
        save_known_docling_ids(known_docling_file, known_docling_ids)

    pipeline_items = pipeline_failures(pipeline_dir)
    recovery_queue.extend(pipeline_items)
    excluded = {item["paper_id"] for item in recovery_queue if item["kind"] == "language_deferred"}
    excluded.update(item["paper_id"] for item in recovery_queue if item["stage"] == "docling")
    recovery_queue.extend(missing_core_outputs(selected, Path(args.library_dir), excluded))

    recovery_actions: list[dict[str, object]] = []
    for pass_index in range(1, max(0, args.max_recovery_passes) + 1):
        pipeline_fail_items = [item for item in recovery_queue if item["stage"] in STAGE_ORDER]
        docling_ids = sorted({item["paper_id"] for item in recovery_queue if item["stage"] == "docling"})
        if args.retry_docling_once and pass_index == 1 and docling_ids:
            code = retry_docling(docling_ids, args, run_dir, pass_index)
            recovery_actions.append({"pass": pass_index, "action": "retry_docling_serial", "paper_ids": docling_ids, "code": code})
        if pipeline_fail_items:
            code = retry_pipeline_stages(pipeline_fail_items, args, run_dir, pass_index)
            recovery_actions.append({"pass": pass_index, "action": "retry_pipeline_stage_force", "code": code})

    final_docling_missing = sorted({item["paper_id"] for item in recovery_queue if item["stage"] == "docling"})
    # Recompute final missing state after recovery attempts. Known/failed Docling papers
    # are expected exclusions, not core-output failures.
    final_excluded = {item["paper_id"] for item in recovery_queue if item["kind"] == "language_deferred"}
    final_excluded.update(final_docling_missing)
    final_missing = missing_core_outputs(selected, Path(args.library_dir), final_excluded)
    final_excluded.update(final_docling_missing)
    validate_code = validate_core(selected, final_excluded, args, run_dir)

    report = {
        "run_dir": str(run_dir),
        "mode": "run",
        "main_exit_code": main_code,
        "selected_count": len(selected),
        "selected_papers": selected,
        "language_deferred": sorted({item["paper_id"] for item in recovery_queue if item["kind"] == "language_deferred"}),
        "docling_unresolved": sorted(final_docling_missing),
        "final_missing_outputs": final_missing,
        "validation_exit_code": validate_code,
        "recovery_actions": recovery_actions,
        "recovery_queue": recovery_queue,
        "content_cjk_threshold": CONTENT_CJK_DEFER_THRESHOLD,
        "known_docling_file": str(known_docling_file),
    }
    write_report(run_dir, report)

    hard_failures = final_missing or validate_code != 0
    if hard_failures:
        print("Workflow finished with unresolved items. See final_report.json.")
        return 1
    print("Workflow finished successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
