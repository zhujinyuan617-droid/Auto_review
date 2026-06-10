"""CJK language gate: defer Chinese-body PDFs at import instead of crashing.

Fixes the new-import path of ISSUES I17 (PyMuPDF shreds CJK into thousands of
blocks -> sections stage output overflows -> AIClientError crash). Ratio rule
follows the I8 cleanup convention: >=15% CJK characters (vs CJK+ASCII letters).
"""
from __future__ import annotations

import json
from pathlib import Path

CJK_THRESHOLD = 0.15

_CJK_RANGES = ((0x4E00, 0x9FFF), (0x3400, 0x4DBF))


def _is_cjk(ch: str) -> bool:
    code = ord(ch)
    return any(lo <= code <= hi for lo, hi in _CJK_RANGES)


def cjk_ratio(text: str) -> float:
    cjk = sum(1 for ch in text if _is_cjk(ch))
    ascii_letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    denom = cjk + ascii_letters
    return (cjk / denom) if denom else 0.0


def check_package_language(paper_dir: Path) -> dict:
    content = json.loads((paper_dir / "content_blocks.json").read_text(encoding="utf-8"))
    text = "\n".join((b.get("text") or "") for b in content.get("blocks") or [])
    ratio = cjk_ratio(text)
    return {"status": "deferred_cjk" if ratio >= CJK_THRESHOLD else "ok",
            "cjk_ratio": round(ratio, 4), "deferred": ratio >= CJK_THRESHOLD}
