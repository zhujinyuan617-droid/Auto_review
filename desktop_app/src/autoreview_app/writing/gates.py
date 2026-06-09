from __future__ import annotations

from typing import Any

from .. import engine_bridge

engine_bridge.ensure_engine_write_on_path()  # adds Document_Decomposer/scripts/write to sys.path

import run_writing_loop as _writing_loop  # engine module (now importable)  # noqa: E402


def check_draft(draft_text: str) -> dict[str, Any]:
    """Run the engine's mechanical citation gate + style gate on a draft string.

    Pure: no AI, no file I/O. Returns {"citation": {...}, "style": {...}} where
    citation.passed is the hard gate and style.warnings is advisory (non-fatal).
    """
    return {
        "citation": _writing_loop.citation_gate(draft_text),
        "style": _writing_loop.style_gate(draft_text),
    }
