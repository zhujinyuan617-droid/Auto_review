from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.paper_profile import classify_record, profile_label

DEFAULT_MANIFEST = ROOT / "data" / "ingest" / "paper_manifest.json"
DEFAULT_STAGING_DIR = ROOT / "data" / "ingest" / "pdfs"
DEFAULT_DOCLING = ROOT / "envs" / "docling" / "Scripts" / "docling.exe"


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


def default_paper_source() -> Path:
    return ROOT.parent / "paper_pool" / "paper"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ingest downloaded PDFs, run missing Docling conversions, then run the Document Decomposer pipeline."
    )
    parser.add_argument("--paper-id", action="append", help="Paper id to process. May be repeated.")
    parser.add_argument("--all", action="store_true", help="Process all active papers in the ingest manifest.")
    parser.add_argument(
        "--source-dir",
        action="append",
        default=[],
        help="PDF source dir/file for ingest. May be repeated. Defaults to ../paper_pool/paper.",
    )
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    parser.add_argument("--staging-dir", default=str(DEFAULT_STAGING_DIR))
    parser.add_argument("--json-dir", default=str(ROOT / "data" / "docling" / "json"))
    parser.add_argument("--md-dir", default=str(ROOT / "data" / "docling" / "md"))
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    parser.add_argument("--config", default=None, help="Path to ai.local.json for AI stages.")
    parser.add_argument("--baseline", default=None, help="Manual synthesis baseline JSON passed to run_pipeline.py.")
    parser.add_argument(
        "--docling-cmd",
        default=None,
        help="Docling executable. Defaults to PATH docling, then envs/docling/Scripts/docling.exe.",
    )
    parser.add_argument(
        "--docling-extra-arg",
        action="append",
        default=[],
        help="Extra argument passed to docling. May be repeated.",
    )
    parser.add_argument("--skip-ingest", action="store_true", help="Use existing manifest without rescanning PDFs.")
    parser.add_argument("--skip-docling", action="store_true", help="Do not run Docling even if outputs are missing.")
    parser.add_argument("--skip-pipeline", action="store_true", help="Do not run run_pipeline.py after Docling.")
    parser.add_argument(
        "--include-possible-duplicates",
        action="store_true",
        help="Process manifest records flagged as possible duplicates.",
    )
    parser.add_argument(
        "--include-deferred",
        action="store_true",
        help="Include deferred non-English or non-article records when --all is used.",
    )
    parser.add_argument("--resume", action="store_true", help="Pass --resume to run_pipeline.py.")
    parser.add_argument("--force", action="store_true", help="Pass --force to run_pipeline.py.")
    parser.add_argument("--parallel", type=int, default=1, help="Pass --parallel to run_pipeline.py.")
    parser.add_argument(
        "--docling-parallel",
        type=int,
        default=1,
        help="Number of Docling conversions to run concurrently. Keep below --parallel; each Docling "
        "process loads layout/table models and is RAM-heavy.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Pass --limit to ingest when rescanning.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned commands without running them.")
    return parser.parse_args()


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def command_text(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.tmp-{os.getpid()}-{uuid4().hex}")
    try:
        temp_path.write_text(text, encoding="utf-8")
        temp_path.replace(path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def atomic_copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f".{target.name}.tmp-{os.getpid()}-{uuid4().hex}")
    try:
        shutil.copy2(source, temp_path)
        temp_path.replace(target)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def run_command(command: list[str], dry_run: bool, log_path: Path | None = None) -> int:
    print(command_text(command))
    if dry_run:
        return 0
    env = os.environ.copy()
    env.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
    env.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, env=env)
    if log_path:
        output = f"$ {command_text(command)}\n\n"
        if completed.stdout:
            output += completed.stdout
        if completed.stderr:
            output += "\n[stderr]\n" + completed.stderr
        atomic_write_text(log_path, output)
    else:
        if completed.stdout:
            print(completed.stdout, end="")
        if completed.stderr:
            print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def find_docling_command(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    path_docling = shutil.which("docling")
    if path_docling:
        return path_docling
    if DEFAULT_DOCLING.exists():
        return str(DEFAULT_DOCLING)
    return None


def staged_pdf_path(record: dict, staging_dir: Path) -> Path | None:
    staged = str(record.get("staged_pdf") or "")
    if staged:
        path = Path(staged)
        return path if path.is_absolute() else ROOT / path
    original = str(record.get("original_path") or "")
    return Path(original) if original else None


def selected_records(
    manifest: dict,
    paper_ids: list[str] | None,
    use_all: bool,
    include_possible_duplicates: bool,
    include_deferred: bool,
) -> list[dict]:
    if paper_ids:
        wanted = {paper_id.upper() for paper_id in paper_ids}
        selected = [
            record
            for record in manifest.get("papers") or []
            if str(record.get("paper_id") or "").upper() in wanted
        ]
    elif use_all:
        records = [
            record
            for record in manifest.get("papers") or []
            if record.get("status") in {"active", "deferred"}
        ]
        selected = records
        if not include_deferred:
            deferred = [record for record in selected if classify_record(record).is_deferred or record.get("status") == "deferred"]
            for record in deferred:
                print(
                    f"Skipping deferred paper {profile_label(record)}. "
                    "Use --include-deferred to process deferred records."
                )
            selected = [
                record
                for record in selected
                if not classify_record(record).is_deferred and record.get("status") != "deferred"
            ]
    else:
        selected = []
    missing = []
    if paper_ids:
        found = {str(record.get("paper_id") or "").upper() for record in selected}
        missing = [paper_id for paper_id in wanted if paper_id not in found]
    for paper_id in missing:
        print(f"Paper id not found in manifest: {paper_id}")
    if include_possible_duplicates:
        return selected
    skipped = [record for record in selected if record.get("possible_duplicate_of")]
    for record in skipped:
        print(
            f"Skipping possible duplicate {record.get('paper_id')} "
            f"(possible_duplicate_of={','.join(record.get('possible_duplicate_of') or [])}). "
            "Use --include-possible-duplicates to process it."
        )
    return [record for record in selected if not record.get("possible_duplicate_of")]


def docling_outputs_for_paper(paper_id: str, json_dir: Path, md_dir: Path) -> tuple[list[Path], list[Path]]:
    json_matches = sorted(json_dir.glob(f"{paper_id}_*.json"))
    md_matches = sorted(md_dir.glob(f"{paper_id}_*.md"))
    return json_matches, md_matches


def copy_docling_outputs(temp_dir: Path, json_dir: Path, md_dir: Path) -> tuple[int, int]:
    json_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)
    json_count = 0
    md_count = 0
    for path in temp_dir.rglob("*.json"):
        atomic_copy_file(path, json_dir / path.name)
        json_count += 1
    for path in temp_dir.rglob("*.md"):
        atomic_copy_file(path, md_dir / path.name)
        md_count += 1
    return json_count, md_count


def ingest_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "ingest_paper_downloads.py"),
        "--manifest",
        str(Path(args.manifest)),
        "--staging-dir",
        str(Path(args.staging_dir)),
    ]
    for source in args.source_dir or [str(default_paper_source())]:
        command.extend(["--source-dir", str(Path(source))])
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    if args.dry_run:
        command.append("--dry-run")
    return command


def run_docling_for_record(
    record: dict,
    docling_cmd: str,
    args: argparse.Namespace,
    run_dir: Path,
) -> int:
    paper_id = str(record["paper_id"])
    pdf_path = staged_pdf_path(record, Path(args.staging_dir))
    if not pdf_path or not pdf_path.exists():
        print(f"{paper_id}: missing staged/original PDF: {pdf_path}")
        return 1

    temp_dir = run_dir / "docling" / paper_id
    command = [
        docling_cmd,
        str(pdf_path),
        "--from",
        "pdf",
        "--to",
        "md",
        "--to",
        "json",
        "--output",
        str(temp_dir),
        "--no-ocr",
        *args.docling_extra_arg,
    ]
    code = run_command(command, args.dry_run, run_dir / "logs" / f"{paper_id}_docling.log")
    if code != 0 or args.dry_run:
        return code
    json_count, md_count = copy_docling_outputs(temp_dir, Path(args.json_dir), Path(args.md_dir))
    print(f"{paper_id}: copied Docling outputs json={json_count}, md={md_count}")
    return 0 if json_count and md_count else 1


def pipeline_command(records: list[dict], args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_pipeline.py"),
        "--stage",
        "all",
        "--json-dir",
        str(Path(args.json_dir)),
        "--md-dir",
        str(Path(args.md_dir)),
        "--library-dir",
        str(Path(args.library_dir)),
        "--reports-dir",
        str(Path(args.reports_dir)),
        "--parallel",
        str(max(1, args.parallel)),
        "--pdf-dir",
        str(Path(args.staging_dir)),
        "--pdf-dir",
        str(default_paper_source()),
    ]
    for record in records:
        command.extend(["--paper-id", str(record["paper_id"])])
    if args.config:
        command.extend(["--config", str(Path(args.config))])
    if args.baseline:
        command.extend(["--baseline", str(Path(args.baseline))])
    if args.resume:
        command.append("--resume")
    if args.force:
        command.append("--force")
    if args.dry_run:
        command.append("--dry-run")
    return command


def main() -> int:
    safe_console()
    args = parse_args()
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid4().hex[:8]}"
    run_dir = Path(args.reports_dir) / f"from_downloads_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_ingest:
        code = run_command(ingest_command(args), args.dry_run, run_dir / "logs" / "ingest.log")
        if code != 0:
            return code

    manifest = load_manifest(Path(args.manifest))
    records = selected_records(
        manifest,
        args.paper_id,
        args.all,
        args.include_possible_duplicates,
        args.include_deferred,
    )
    if not records:
        print("No papers selected. Use --paper-id, --all, or run ingest first.")
        return 2

    missing_docling = []
    for record in records:
        paper_id = str(record["paper_id"])
        json_matches, md_matches = docling_outputs_for_paper(paper_id, Path(args.json_dir), Path(args.md_dir))
        if not json_matches or not md_matches:
            missing_docling.append(record)

    print(f"Selected papers: {', '.join(str(record['paper_id']) for record in records)}")
    print(f"Missing Docling outputs: {', '.join(str(record['paper_id']) for record in missing_docling) or 'none'}")

    if missing_docling and not args.skip_docling:
        docling_cmd = find_docling_command(args.docling_cmd)
        if not docling_cmd:
            print(
                "Docling is not available. Install/provide it with --docling-cmd, "
                "or create envs/docling as described in DOCLING_INSTALL.md.",
                file=sys.stderr,
            )
            return 3
        docling_workers = max(1, args.docling_parallel)
        failed_docling: list[str] = []
        if docling_workers == 1 or len(missing_docling) == 1:
            for record in missing_docling:
                if run_docling_for_record(record, docling_cmd, args, run_dir) != 0:
                    failed_docling.append(str(record["paper_id"]))
        else:
            print(f"Running Docling with {docling_workers} concurrent workers.")
            with ThreadPoolExecutor(max_workers=docling_workers) as executor:
                futures = {
                    executor.submit(run_docling_for_record, record, docling_cmd, args, run_dir): record
                    for record in missing_docling
                }
                for future in as_completed(futures):
                    record = futures[future]
                    try:
                        code = future.result()
                    except Exception as exc:  # keep the batch alive if one paper crashes
                        print(f"{record['paper_id']}: docling crashed: {exc}", file=sys.stderr)
                        code = 1
                    if code != 0:
                        failed_docling.append(str(record["paper_id"]))
        if failed_docling:
            failed_set = {paper_id.upper() for paper_id in failed_docling}
            print(f"Docling failed for: {', '.join(sorted(failed_docling))}. Skipping them in the pipeline.")
            records = [record for record in records if str(record["paper_id"]).upper() not in failed_set]
            if not records:
                print("All selected papers failed Docling; nothing to run in pipeline.")
                return 4
    elif missing_docling:
        print("Skipping Docling; pipeline may fail for papers without JSON/MD outputs.")

    if not args.skip_pipeline:
        code = run_command(pipeline_command(records, args), args.dry_run, run_dir / "logs" / "pipeline.log")
        if code != 0:
            return code

    print(f"Run directory: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
