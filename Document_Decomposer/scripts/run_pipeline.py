from __future__ import annotations

import argparse
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.io_utils import atomic_write_text
from docdecomp.library_index import write_library_index
from docdecomp.paper_profile import CONTENT_CJK_DEFER_THRESHOLD, cjk_ratio


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


@dataclass
class StageResult:
    paper_id: str
    stage: str
    status: str
    log_path: Path | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Document Decomposer pipeline.")
    parser.add_argument("--paper-id", action="append", help="Paper id to process. May be repeated.")
    parser.add_argument("--all", action="store_true", help="Process all paper ids found in --json-dir.")
    parser.add_argument(
        "--stage",
        choices=[
            "all",
            "clean",
            "sections",
            "reading",
            "card",
            "evidence_atoms",
            "paper_syntheses",
            "validate",
        ],
        default="all",
        help="Pipeline stage to run.",
    )
    parser.add_argument("--json-dir", default=str(ROOT / "data" / "docling" / "json"))
    parser.add_argument("--md-dir", default=str(ROOT / "data" / "docling" / "md"))
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument(
        "--pdf-dir",
        action="append",
        default=[],
        help="Directory or PDF file used by build_clean_package.py. May be repeated.",
    )
    parser.add_argument("--config", default=None, help="Path to ai.local.json for AI stages.")
    parser.add_argument(
        "--baseline",
        default=None,
        help="Optional manual synthesis baseline JSON passed to ai_build_paper_syntheses.py.",
    )
    parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    parser.add_argument("--parallel", type=int, default=1, help="Number of papers to process concurrently.")
    parser.add_argument("--resume", action="store_true", help="Skip a stage when its expected outputs already exist.")
    parser.add_argument("--force", action="store_true", help="Force AI stages to refresh and disable runner resume skips.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned commands without running them.")
    return parser.parse_args()


def paper_id_from_stem(stem: str) -> str:
    return stem.split("_", 1)[0]


def discover_paper_ids(args: argparse.Namespace) -> list[str]:
    if args.paper_id:
        return list(dict.fromkeys(args.paper_id))
    if args.all:
        json_dir = Path(args.json_dir)
        return sorted({paper_id_from_stem(path.stem) for path in json_dir.glob("*.json") if path.is_file()})
    library_dir = Path(args.library_dir)
    if library_dir.exists():
        return sorted(path.name for path in library_dir.iterdir() if path.is_dir())
    return []


def selected_paper_stages(stage: str) -> list[str]:
    if stage == "all":
        return list(STAGE_ORDER)
    if stage == "validate":
        return []
    return [stage]


def stage_outputs(paper_id: str, stage: str, args: argparse.Namespace) -> list[Path]:
    paper_dir = Path(args.library_dir) / paper_id
    return {
        "clean": [
            paper_dir / "content_blocks.json",
            paper_dir / "evidence.json",
            paper_dir / "metadata_candidates.json",
            paper_dir / "content.md",
        ],
        "sections": [paper_dir / "ai_sections.json"],
        "reading": [
            paper_dir / "reading_blocks.plan.json",
            paper_dir / "reading_blocks.json",
            paper_dir / "reading.md",
            paper_dir / "merge_report.json",
        ],
        "card": [paper_dir / "literature_card.json"],
        "evidence_atoms": [paper_dir / "evidence_atoms.json"],
        "paper_syntheses": [paper_dir / "paper_syntheses.json"],
    }[stage]


def command_for_stage(paper_id: str, stage: str, args: argparse.Namespace, run_dir: Path) -> list[str]:
    command = [sys.executable]
    if stage == "clean":
        command.extend(
            [
                str(ROOT / "scripts" / "build_clean_package.py"),
                "--json-dir",
                str(Path(args.json_dir)),
                "--md-dir",
                str(Path(args.md_dir)),
                "--output-dir",
                str(Path(args.library_dir)),
                "--paper-id",
                paper_id,
                "--report",
                str(run_dir / f"clean_package_{paper_id}.csv"),
            ]
        )
        for pdf_dir in args.pdf_dir:
            command.extend(["--pdf-dir", str(Path(pdf_dir))])
        return command

    script_by_stage = {
        "sections": "ai_organize_sections.py",
        "reading": "ai_build_reading_blocks.py",
        "card": "ai_build_literature_card.py",
        "evidence_atoms": "ai_build_evidence_atoms.py",
        "paper_syntheses": "ai_build_paper_syntheses.py",
    }
    command.extend(
        [
            str(ROOT / "scripts" / script_by_stage[stage]),
            "--paper-id",
            paper_id,
            "--library-dir",
            str(Path(args.library_dir)),
        ]
    )
    if args.config:
        command.extend(["--config", str(Path(args.config))])
    max_attempts_by_stage = {
        "card": "4",
        "evidence_atoms": "5",
        "paper_syntheses": "6",
    }
    if stage in max_attempts_by_stage:
        command.extend(["--max-ai-attempts", max_attempts_by_stage[stage]])
    if stage == "paper_syntheses" and args.baseline:
        command.extend(["--baseline", str(Path(args.baseline))])
    if args.force:
        command.append("--force")
    return command


def command_text(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in part else part for part in command)


def run_command(command: list[str], log_path: Path, dry_run: bool) -> int:
    header = f"$ {command_text(command)}\n\n"
    if dry_run:
        atomic_write_text(log_path, header + "[dry-run]\n")
        print(command_text(command))
        return 0

    completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    output = header
    if completed.stdout:
        output += completed.stdout
    if completed.stderr:
        output += "\n[stderr]\n" + completed.stderr
    atomic_write_text(log_path, output)
    return completed.returncode


def run_stage(paper_id: str, stage: str, args: argparse.Namespace, run_dir: Path) -> StageResult:
    outputs = stage_outputs(paper_id, stage, args)
    if args.resume and not args.force and all(path.exists() for path in outputs):
        return StageResult(paper_id=paper_id, stage=stage, status="skipped")

    log_path = run_dir / "logs" / f"{paper_id}_{stage}.log"
    command = command_for_stage(paper_id, stage, args, run_dir)
    code = run_command(command, log_path, args.dry_run)
    status = "ok" if code == 0 else f"failed:{code}"
    return StageResult(paper_id=paper_id, stage=stage, status=status, log_path=log_path)


def _content_cjk_ratio(paper_dir: Path) -> float:
    content = paper_dir / "content.md"
    if not content.exists():
        return 0.0
    try:
        return cjk_ratio(content.read_text(encoding="utf-8"))
    except OSError:
        return 0.0


def run_paper(paper_id: str, stages: list[str], args: argparse.Namespace, run_dir: Path) -> list[StageResult]:
    results: list[StageResult] = []
    for stage in stages:
        result = run_stage(paper_id, stage, args, run_dir)
        results.append(result)
        if result.status.startswith("failed"):
            break
        # Language gate: after the clean package exists, defer bilingual/Chinese
        # papers before spending AI on them (the filename classifier cannot see a
        # Chinese body behind an English title; see S85).
        if stage == "clean":
            ratio = _content_cjk_ratio(Path(args.library_dir) / paper_id)
            if ratio > CONTENT_CJK_DEFER_THRESHOLD:
                results.append(
                    StageResult(
                        paper_id=paper_id,
                        stage="language_gate",
                        status=f"deferred:non_english_content_cjk_{ratio:.0%}",
                    )
                )
                break
    return results


def run_validation(paper_ids: list[str], args: argparse.Namespace, run_dir: Path) -> list[StageResult]:
    results: list[StageResult] = []
    if not paper_ids:
        return results

    common_ids = [item for paper_id in paper_ids for item in ["--paper-id", paper_id]]
    validators = [
        (
            "validate_reading",
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_reading_blocks.py"),
                "--library-dir",
                str(Path(args.library_dir)),
                *common_ids,
                "--report",
                str(run_dir / "reading_blocks_quality.csv"),
            ],
        ),
        (
            "validate_card",
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_literature_card.py"),
                "--library-dir",
                str(Path(args.library_dir)),
                *common_ids,
                "--report",
                str(run_dir / "literature_card_quality.csv"),
            ],
        ),
        (
            "validate_evidence_atoms",
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_evidence_atoms.py"),
                "--library-dir",
                str(Path(args.library_dir)),
                *common_ids,
                "--report",
                str(run_dir / "evidence_atoms_quality.csv"),
            ],
        ),
        (
            "validate_paper_syntheses",
            [
                sys.executable,
                str(ROOT / "scripts" / "validate_paper_syntheses.py"),
                "--library-dir",
                str(Path(args.library_dir)),
                *common_ids,
                "--report",
                str(run_dir / "paper_syntheses_quality.csv"),
            ],
        ),
    ]
    for stage, command in validators:
        log_path = run_dir / "logs" / f"{stage}.log"
        code = run_command(command, log_path, args.dry_run)
        status = "ok" if code == 0 else f"failed:{code}"
        results.append(StageResult(paper_id="*", stage=stage, status=status, log_path=log_path))
    return results


def write_summary(run_dir: Path, results: list[StageResult]) -> None:
    lines = ["paper_id,stage,status,log_path"]
    for result in results:
        lines.append(
            ",".join(
                [
                    result.paper_id,
                    result.stage,
                    result.status,
                    str(result.log_path or ""),
                ]
            )
        )
    atomic_write_text(run_dir / "pipeline_summary.csv", "\n".join(lines) + "\n")


def main() -> int:
    safe_console()
    args = parse_args()
    paper_ids = discover_paper_ids(args)
    if not paper_ids:
        print("No paper ids selected. Use --paper-id or --all.")
        return 2

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    run_id = f"{timestamp}_{os.getpid()}_{uuid4().hex[:8]}"
    run_dir = Path(args.reports_dir) / f"pipeline_{run_id}"
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    stages = selected_paper_stages(args.stage)
    results: list[StageResult] = []
    if stages:
        parallel = max(1, args.parallel)
        if parallel == 1 or len(paper_ids) == 1:
            for paper_id in paper_ids:
                results.extend(run_paper(paper_id, stages, args, run_dir))
        else:
            with ThreadPoolExecutor(max_workers=parallel) as executor:
                future_map = {
                    executor.submit(run_paper, paper_id, stages, args, run_dir): paper_id
                    for paper_id in paper_ids
                }
                for future in as_completed(future_map):
                    results.extend(future.result())

    if args.stage in {"all", "validate"}:
        failed_papers = {
            result.paper_id
            for result in results
            if result.paper_id != "*" and result.status.startswith("failed")
        }
        validation_ids = paper_ids if args.stage == "validate" else [
            paper_id for paper_id in paper_ids if paper_id not in failed_papers
        ]
        results.extend(run_validation(validation_ids, args, run_dir))

    write_summary(run_dir, results)
    print(f"Run directory: {run_dir}")
    if args.dry_run:
        print(f"Library index: {Path(args.library_dir) / 'index.csv'} (dry-run, not refreshed)")
    else:
        index_rows = write_library_index(Path(args.library_dir))
        print(f"Library index: {Path(args.library_dir) / 'index.csv'} ({len(index_rows)} papers)")
    for result in results:
        print(f"{result.paper_id} {result.stage}: {result.status}")

    failed = [result for result in results if result.status.startswith("failed")]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
