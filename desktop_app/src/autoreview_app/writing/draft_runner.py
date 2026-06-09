from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

from .. import engine_bridge
from .loop import run_writing_loop


def build_brief_via_engine(selection: dict[str, Any], run_dir: Path) -> dict[str, Any]:
    """Build a grounded writing brief by invoking the engine's build_writing_brief.py
    as a subprocess against the engine tree, then read brief.json back."""
    engine_root = engine_bridge.ENGINE_SRC.parent  # Document_Decomposer/
    script = engine_root / "scripts" / "write" / "build_writing_brief.py"
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "brief.json"
    cmd = [sys.executable, str(script), "--out", str(out),
           "--section-count", str(selection.get("section_count", 1)),
           "--word-target", str(selection.get("word_target", 300))]
    if selection.get("topic"):
        cmd += ["--topic", str(selection["topic"])]
    for pid in selection.get("paper_ids", []):
        cmd += ["--paper-id", str(pid)]
    for c in selection.get("concepts", []):
        cmd += ["--concept", str(c)]
    subprocess.run(cmd, cwd=str(engine_root), check=True, capture_output=True, text=True)
    return json.loads(out.read_text(encoding="utf-8"))


def run_draft(
    selection: dict[str, Any],
    library_dir: Path,
    client_factory: Callable[[], Any],
    progress: Callable[[str], None],
    max_rounds: int = 2,
) -> dict[str, Any]:
    """Build a grounded brief from the selection, run the writing loop, and return
    the loop summary enriched with the produced draft text."""
    run_dir = library_dir.parent / "writing" / "run"
    progress("building brief")
    brief = build_brief_via_engine(selection, run_dir)
    progress("running writing loop")
    client = client_factory()
    summary = run_writing_loop(brief, run_dir, max_rounds, client, client)
    history = summary.get("history") or []
    draft_text = ""
    if history:
        draft_path = Path(history[-1].get("draft_path", ""))
        if draft_path.is_file():
            draft_text = draft_path.read_text(encoding="utf-8")
    summary["draft_text"] = draft_text
    summary["run_dir"] = str(run_dir)
    progress("done")
    return summary
