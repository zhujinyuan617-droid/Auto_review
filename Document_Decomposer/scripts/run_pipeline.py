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

from docdecomp.io_utils import atomic_write_text, write_json
from docdecomp.library_index import write_library_index
from docdecomp.paper_profile import CONTENT_CJK_DEFER_THRESHOLD, cjk_ratio


STAGE_ORDER = ["clean", "sections", "reading", "card", "elements", "card_tags"]
LEGACY_STAGES = ["evidence_atoms", "paper_syntheses"]


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
        choices=["all"] + STAGE_ORDER + LEGACY_STAGES + ["validate"],
        default="all",
        help="Pipeline stage to run.",
    )
    parser.add_argument(
        "--include-legacy-stages",
        action="store_true",
        help="Run v1 evidence_atoms/paper_syntheses after card.",
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


def effective_stage_order(args: argparse.Namespace) -> list[str]:
    """Return the active ordered stage list, splicing in legacy stages when flag set."""
    if args.include_legacy_stages:
        card_idx = STAGE_ORDER.index("card")
        return STAGE_ORDER[: card_idx + 1] + LEGACY_STAGES + STAGE_ORDER[card_idx + 1 :]
    return list(STAGE_ORDER)


def selected_paper_stages(stage: str, args: argparse.Namespace) -> list[str]:
    if stage == "all":
        return effective_stage_order(args)
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
        "elements": [paper_dir / "elements.json"],
        "card_tags": [paper_dir / "literature_card.json"],
        "evidence_atoms": [paper_dir / "evidence_atoms.json"],
        "paper_syntheses": [paper_dir / "paper_syntheses.json"],
    }[stage]


_CARD_TAGS_SENTINEL = "__card_tags_in_process__"


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

    if stage == "elements":
        command.extend(
            [
                str(ROOT / "scripts" / "elements" / "ai_extract_elements.py"),
                "--paper",
                paper_id,
                "--library-dir",
                str(Path(args.library_dir)),
            ]
        )
        if args.config:
            command.extend(["--config", str(Path(args.config))])
        if args.force:
            command.append("--force")
        return command

    if stage == "card_tags":
        # Handled in-process in run_stage; return a sentinel list so callers know
        # not to subprocess this stage.
        return [_CARD_TAGS_SENTINEL]

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


def _run_card_tags_in_process(paper_id: str, args: argparse.Namespace, log_path: Path) -> StageResult:
    """Apply card_tags derivation in-process (no subprocess, no AI)."""
    import json as _json

    paper_dir = Path(args.library_dir) / paper_id
    registry_path = ROOT / "data" / "elements" / "registry.json"
    if not registry_path.exists():
        msg = f"skipped: registry not found at {registry_path}"
        atomic_write_text(log_path, msg + "\n")
        return StageResult(paper_id=paper_id, stage="card_tags", status="skipped")

    elements_path = paper_dir / "elements.json"
    if not elements_path.exists():
        msg = f"skipped: elements.json not found for {paper_id}"
        atomic_write_text(log_path, msg + "\n")
        return StageResult(paper_id=paper_id, stage="card_tags", status="skipped")

    card_path = paper_dir / "literature_card.json"
    if not card_path.exists():
        msg = f"skipped: literature_card.json not found for {paper_id}"
        atomic_write_text(log_path, msg + "\n")
        return StageResult(paper_id=paper_id, stage="card_tags", status="skipped")

    try:
        from docdecomp.element_registry import load_registry
        from docdecomp.card_tags import derive_classification, apply_derived_tags, derive_topic_ids

        registry = load_registry(registry_path)
        elements_doc = _json.loads(elements_path.read_text(encoding="utf-8"))
        card = _json.loads(card_path.read_text(encoding="utf-8"))

        derived = derive_classification(elements_doc, registry)
        apply_derived_tags(card, derived)
        topic_ids = derive_topic_ids(card, registry)
        card.setdefault("classification", {})["topic_ids"] = topic_ids

        write_json(card_path, card)
        msg = (
            f"card_tags ok: research_objects={derived['research_objects']}, "
            f"methods={derived['methods']}, topic_ids={topic_ids}"
        )
        atomic_write_text(log_path, msg + "\n")
        return StageResult(paper_id=paper_id, stage="card_tags", status="ok", log_path=log_path)
    except Exception as exc:  # noqa: BLE001
        msg = f"card_tags failed: {type(exc).__name__}: {exc}"
        atomic_write_text(log_path, msg + "\n")
        return StageResult(paper_id=paper_id, stage="card_tags", status=f"failed:1", log_path=log_path)


def run_stage(paper_id: str, stage: str, args: argparse.Namespace, run_dir: Path) -> StageResult:
    outputs = stage_outputs(paper_id, stage, args)
    if args.resume and not args.force and all(path.exists() for path in outputs):
        return StageResult(paper_id=paper_id, stage=stage, status="skipped")

    log_path = run_dir / "logs" / f"{paper_id}_{stage}.log"

    # card_tags is an in-process step — no subprocess
    if stage == "card_tags":
        if args.dry_run:
            registry_path = ROOT / "data" / "elements" / "registry.json"
            print(f"[card_tags in-process] paper={paper_id} registry={registry_path}")
            atomic_write_text(log_path, "[dry-run]\n")
            return StageResult(paper_id=paper_id, stage="card_tags", status="ok", log_path=log_path)
        return _run_card_tags_in_process(paper_id, args, log_path)

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
    ]
    # Legacy validators: only run when legacy stages are included
    if args.include_legacy_stages:
        validators.extend(
            [
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
        )
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

    stages = selected_paper_stages(args.stage, args)
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
        if args.stage == "validate":
            validation_ids = paper_ids
        else:
            completed_papers = {
                result.paper_id
                for result in results
                if result.stage == STAGE_ORDER[-1] and result.status in {"ok", "skipped"}
            }
            validation_ids = [
                paper_id
                for paper_id in paper_ids
                if paper_id in completed_papers and paper_id not in failed_papers
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
