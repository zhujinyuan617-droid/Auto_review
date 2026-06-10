"""Mechanical number+unit extraction from a digits-verified verbatim quote.

Never invents: only regex over the quote text. Ranges keep the raw span (0.1-30).

Known limitations (accepted, prefer-miss-over-wrong):
- Signed numbers are skipped entirely ("-10 °C" extracts nothing).
- Bare h/K units can false-positive on label-like text ("Table 4 h"); the
  caller-side facet gate (condition quotes only) is the real guard.
- Zero spaces between number and unit is accepted ("25MPa") — PDF extraction
  often loses the space.
"""
from __future__ import annotations

import re

_NUM = r"\d+(?:\.\d+)?"
_RANGE = rf"{_NUM}(?:\s*[-–—~]\s*{_NUM})?"
_UNITS = (
    r"°C|°F|K\b|MPa|GPa|kPa|bar\b|atm\b|psi\b|rpm\b|wt\.?%|vol\.?%|%|"
    r"nm\b|µm|μm|mm\b|cm³/g|cm3/g|mmol/g|mg/g|m²/g|m2/g|h\b|hr\b|hours?\b|min\b"
)
_PATTERN = re.compile(rf"(?<![\d.\-])(?P<num>{_RANGE})\s*(?P<unit>{_UNITS})")


def parse_values(quote: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in _PATTERN.finditer(quote):
        num = re.sub(r"\s*[-–—~]\s*", "-", m.group("num"))
        out.append({"raw": m.group(0).strip(), "unit": m.group("unit"), "num": num})
    return out
