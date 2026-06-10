from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.io_utils import atomic_write_text, write_json


CONN = ROOT / "reports" / "connection"
DEFAULT_CONFIG = "config\\ai.local.json"


@dataclass
class StepResult:
    name: str
    command: list[str]
    code: int
    log_path: Path
    output: str


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


def quote(value: str) -> str:
    if " " in value or "\t" in value:
        return f'"{value}"'
    return value


def command_text(command: list[str]) -> str:
    return " ".join(quote(part) for part in command)


def child_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    return env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Update the review workspace: optional extraction recovery, then connection "
            "rebuild, graph export, and AI angle proposal."
        )
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to local AI config.")
    parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    parser.add_argument("--skip-extraction", action="store_true", help="Use existing library outputs.")
    parser.add_argument("--skip-connection", action="store_true", help="Do not rebuild vocabulary/edges/index.")
    parser.add_argument("--skip-graph", action="store_true", help="Do not rebuild graph.html.")
    parser.add_argument("--skip-angles", action="store_true", help="Do not ask AI to propose angles.")
    parser.add_argument("--parallel", type=int, default=6, help="Pipeline workers for extraction recovery.")
    parser.add_argument("--docling-parallel", type=int, default=2, help="Docling workers for extraction recovery.")
    parser.add_argument("--max-recovery-passes", type=int, default=1)
    parser.add_argument(
        "--retry-docling-once",
        action="store_true",
        help="Retry Docling failures once; default is to mark known bad PDFs and move on.",
    )
    parser.add_argument("--edge-workers", type=int, default=6, help="AI workers for typed edge judging.")
    parser.add_argument(
        "--edge-source",
        choices=["off", "on"],
        default="off",
        help="Whether ai_build_edges.py also reads abstract/conclusion.",
    )
    parser.add_argument("--force-edges", action="store_true", help="Ignore existing edge cache.")
    parser.add_argument("--angle-n", type=int, default=6, help="Number of candidate angles to request.")
    parser.add_argument("--angle-model", default="deepseek-v4-pro", help="Model for propose_angles.py.")
    parser.add_argument("--dry-run", action="store_true", help="Print and log commands without running them.")
    return parser.parse_args()


def run_step(name: str, command: list[str], log_path: Path, dry_run: bool) -> StepResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"$ {command_text(command)}\n\n"
    print()
    print(f"== {name} ==")
    print(command_text(command))
    sys.stdout.flush()

    if dry_run:
        atomic_write_text(log_path, header + "[dry-run]\n")
        return StepResult(name=name, command=command, code=0, log_path=log_path, output="[dry-run]\n")

    lines: list[str] = []
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=child_env(),
    )
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        lines.append(line)
    code = process.wait()
    output = "".join(lines)
    atomic_write_text(log_path, header + output)
    print(f"== {name} finished: code={code} ==")
    return StepResult(name=name, command=command, code=code, log_path=log_path, output=output)


def extraction_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "run_workflow_with_recovery.py"),
        "--all",
        "--config",
        args.config,
        "--parallel",
        str(args.parallel),
        "--docling-parallel",
        str(args.docling_parallel),
        "--max-recovery-passes",
        str(args.max_recovery_passes),
    ]
    if args.retry_docling_once:
        command.append("--retry-docling-once")
    if args.dry_run:
        command.append("--dry-run")
    return command


def connection_steps(args: argparse.Namespace) -> list[tuple[str, list[str]]]:
    steps: list[tuple[str, list[str]]] = [
        # 词表已退役为注册表纯脚本派生(ISSUES I12/I18):绝不再调 AI 归一的 build_vocabulary
        (
            "derive vocabulary",
            [
                sys.executable,
                str(ROOT / "scripts" / "elements" / "derive_vocabulary.py"),
            ],
        ),
        (
            "build candidate edges",
            [
                sys.executable,
                str(ROOT / "scripts" / "connect" / "build_candidate_edges.py"),
                "--library-dir",
                "library",
            ],
        ),
        (
            "build typed edges",
            [
                sys.executable,
                str(ROOT / "scripts" / "connect" / "ai_build_edges.py"),
                "--config",
                args.config,
                "--workers",
                str(args.edge_workers),
                "--source",
                args.edge_source,
            ],
        ),
        (
            "build concept index",
            [
                sys.executable,
                str(ROOT / "scripts" / "connect" / "build_concept_index.py"),
                "--library-dir",
                "library",
            ],
        ),
    ]
    if args.force_edges:
        steps[2][1].append("--force")
    if not args.skip_graph:
        steps.append(("build graph html", [sys.executable, str(ROOT / "scripts" / "use" / "build_graph_html.py")]))
    return steps


def angle_step(args: argparse.Namespace) -> tuple[str, list[str]]:
    return (
        "propose review angles",
        [
            sys.executable,
            str(ROOT / "scripts" / "use" / "propose_angles.py"),
            "--config",
            args.config,
            "--n",
            str(args.angle_n),
            "--model",
            args.angle_model,
        ],
    )


def parse_recovery_report_path(output: str) -> Path | None:
    matches = re.findall(r"Recovery report:\s*(.+)", output)
    if not matches:
        return None
    value = matches[-1].strip()
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def read_json(path: Path | None) -> dict:
    if not path or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def output_status() -> dict[str, dict[str, object]]:
    paths = {
        "vocabulary": CONN / "vocabulary.json",
        "candidate_edges": CONN / "candidate_edges.json",
        "typed_edges": CONN / "edges.json",
        "concept_index": CONN / "concept_index.json",
        "graph_html": CONN / "graph.html",
        "angles": CONN / "angles.md",
    }
    status: dict[str, dict[str, object]] = {}
    for name, path in paths.items():
        status[name] = {
            "path": str(path),
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
        }
    return status


def summarize_extraction(report: dict) -> list[str]:
    if not report:
        return ["- Extraction recovery: skipped or report not available"]
    language_deferred = report.get("language_deferred") or []
    docling_unresolved = report.get("docling_unresolved") or []
    final_missing = report.get("final_missing_outputs") or []
    selected_count = int(report.get("selected_count") or 0)
    completed = max(
        0,
        selected_count
        - len(language_deferred)
        - len(docling_unresolved)
        - len({item.get("paper_id") for item in final_missing if item.get("paper_id")}),
    )
    return [
        f"- Selected mainline papers: {selected_count}",
        f"- Completed/planned core papers: {completed}",
        f"- Language/content deferred: {len(language_deferred)}",
        f"- Docling unresolved: {len(docling_unresolved)}",
        f"- Missing core outputs: {len(final_missing)}",
        f"- Validation exit code: {report.get('validation_exit_code', '')}",
    ]


def write_markdown_report(run_dir: Path, report: dict) -> None:
    lines = [
        "# Review Workspace Report",
        "",
        f"- Mode: {report['mode']}",
        f"- Status: {report['status']}",
        f"- Run directory: {run_dir}",
        "",
        "## Steps",
        "",
    ]
    for step in report["steps"]:
        lines.append(f"- {step['name']}: code={step['code']} log={step['log_path']}")

    lines.extend(["", "## Extraction", ""])
    lines.extend(summarize_extraction(report.get("extraction_report") or {}))

    lines.extend(["", "## Workspace Outputs", ""])
    for name, item in report["outputs"].items():
        state = "ok" if item["exists"] else "missing"
        lines.append(f"- {name}: {state} ({item['bytes']} bytes) `{item['path']}`")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- This runner only orchestrates existing scripts. It does not hand-edit AI-generated content.",
            "- Bad PDFs remain the extraction recovery runner's responsibility and are marked rather than repeatedly rescued by default.",
            "- After a successful run, inspect `reports/connection/graph.html` and `reports/connection/angles.md`.",
        ]
    )
    atomic_write_text(run_dir / "workspace_report.md", "\n".join(lines) + "\n")


def write_report(run_dir: Path, report: dict) -> None:
    write_json(run_dir / "workspace_report.json", report)
    write_markdown_report(run_dir, report)
    print()
    print(f"Workspace report: {run_dir / 'workspace_report.json'}")
    print(f"Markdown report: {run_dir / 'workspace_report.md'}")


def main() -> int:
    safe_console()
    args = parse_args()
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid4().hex[:8]}"
    run_dir = Path(args.reports_dir) / f"review_workspace_{run_id}"
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    results: list[StepResult] = []
    extraction_report_path: Path | None = None
    extraction_report: dict = {}

    planned: list[tuple[str, list[str]]] = []
    if not args.skip_extraction:
        planned.append(("extraction recovery", extraction_command(args)))
    if not args.skip_connection:
        planned.extend(connection_steps(args))
    elif not args.skip_graph:
        planned.append(("build graph html", [sys.executable, str(ROOT / "scripts" / "use" / "build_graph_html.py")]))
    if not args.skip_angles:
        planned.append(angle_step(args))

    status = "ok"
    for index, (name, command) in enumerate(planned, start=1):
        log_name = f"{index:02d}_{name.replace(' ', '_')}.log"
        result = run_step(name, command, run_dir / "logs" / log_name, args.dry_run)
        results.append(result)
        if name == "extraction recovery":
            extraction_report_path = parse_recovery_report_path(result.output)
            extraction_report = read_json(extraction_report_path)
        if result.code != 0:
            status = "failed"
            print(f"Stopping after failed step: {name}")
            break

    report = {
        "mode": "dry_run" if args.dry_run else "run",
        "status": status,
        "run_dir": str(run_dir),
        "extraction_report_path": str(extraction_report_path) if extraction_report_path else None,
        "extraction_report": extraction_report,
        "outputs": output_status(),
        "steps": [
            {
                "name": item.name,
                "code": item.code,
                "command": item.command,
                "log_path": str(item.log_path),
            }
            for item in results
        ],
    }
    write_report(run_dir, report)
    if status != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
