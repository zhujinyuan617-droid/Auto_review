"""Verbatim quote verification for research elements.

Two levels (both ellipsis-aware), in the spirit of scripts/audit/audit_card_grounding.py:
- loose  (letters only): proves the sentence exists in the cited block, immune to
  Docling stray digits / punctuation noise.
- tight  (letters+digits): proves digits were not altered; ONLY tight-verified
  quotes may feed numeric value parsing (元原则: 宁可漏, 不可编).
Digit-only fragments (no letters) cannot be existence-checked at the loose level;
they are covered only by the tight check, so a fabricated digit string yields
digits_verified=False (values then never parsed) while quote_verified may stay True.
"""
from __future__ import annotations

import unicodedata

MIN_FRAGMENT_CHARS = 12


def norm_loose(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return "".join(ch.lower() for ch in s if ch.isalpha())


def norm_tight(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return "".join(ch.lower() for ch in s if ch.isalnum())


def _fragments(quote: str) -> list[str]:
    return quote.replace("…", "...").split("...")


def verify_quote(quote: str, block_text: str) -> dict:
    frags = _fragments(quote)
    loose = [norm_loose(f) for f in frags]
    loose = [f for f in loose if len(f) >= MIN_FRAGMENT_CHARS]
    if not loose:
        return {"quote_verified": False, "digits_verified": False, "reason": "too_short"}
    block_loose = norm_loose(block_text)
    if not all(f in block_loose for f in loose):
        return {"quote_verified": False, "digits_verified": False, "reason": "not_found"}
    tight = [norm_tight(f) for f in frags]
    tight = [f for f in tight if len(f) >= MIN_FRAGMENT_CHARS]
    block_tight = norm_tight(block_text)
    digits_ok = bool(tight) and all(f in block_tight for f in tight)
    return {"quote_verified": True, "digits_verified": digits_ok, "reason": ""}
