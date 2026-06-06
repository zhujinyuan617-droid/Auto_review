"""Grounded drafting for a CROSS-PAPER angle (not a single concept).

draft_section.py drafts a subsection about ONE concept (pulls that concept's central
papers from concept_index). Some review theses are not a concept but a pattern that
spans several verified contradictions -- e.g. "the same effect reverses direction
depending on system conditions, and the field lacks a controlled cross-system
comparison". The grounding for such a thesis lives in the verify_*.json files produced
by verify_angle.py: each holds VERIFIED (source-checked, verbatim) quotes plus the
reconciling variable for one pair.

This script reads selected verify_*.json, keeps only the quotes marked verified, and
asks the AI to draft the synthesis subsection under the same discipline as
draft_section: every claim cited [Sxx], every number traceable to a fed quote, no
invention. The condition-dependence is framed as the open gap, not a settled result.

Output: reports/connection/draft_angle_<slug>.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config

CONN = ROOT / "reports" / "connection"

DEFAULT_THESIS = (
    "In confined-fluid simulations, the direction of competitive-adsorption / displacement "
    "outcomes is not universal but REVERSES with system conditions (adsorbent/substrate, length "
    "scale, temperature, fluid phase); apparent inter-study contradictions largely dissolve into "
    "condition-dependence, and the field lacks controlled cross-system comparison (same force "
    "field / same protocol varied across one condition) to unify them."
)


def panel_of(data: dict) -> dict:
    """verify_*.json comes in two shapes: hybrid (has 'final') or single-pass (top-level)."""
    return data.get("final", data)


def load_cases(files: list[Path], keep: set[str]) -> tuple[list[dict], dict]:
    cases, counts = [], {}
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        panel = panel_of(data)
        judge = panel.get("judge", {})
        verdict = judge.get("verdict", "?")
        counts[verdict] = counts.get(verdict, 0) + 1
        if verdict not in keep:
            continue
        ev = (panel.get("prosecutor", {}).get("evidence_checked", [])
              + panel.get("defense", {}).get("evidence_checked", []))
        quotes = [{"paper": e.get("paper", ""), "quote": e.get("quote", "")}
                  for e in ev if e.get("verified")]
        if not quotes:
            continue
        cases.append({
            "papers": data.get("papers", []),
            "verdict": verdict,
            "reconciling_variable": judge.get("reconciling_variable"),
            "verified_quotes": quotes,
        })
    return cases, counts


SYSTEM = (
    "You are drafting ONE subsection of a literature review. A THESIS is supplied. Ground EVERY "
    "statement ONLY in the provided VERIFIED quotes -- each is verbatim source text already checked "
    "to exist in that paper. Rules:\n"
    "1. FACTS COME FROM QUOTES. Every number/quantitative claim MUST appear verbatim in a quote. "
    "Do not write a claim more specific than its quote supports (no added thresholds/units/scope).\n"
    "2. Cite every statement with the paper id, e.g. [S121]. Multiple: [S121; S43].\n"
    "3. The thesis is that an effect REVERSES direction across studies. For each case, state the "
    "two papers' OPPOSING directions and NAME the reconciling variable given for that case, "
    "grounding each side in its quote. Do NOT call them flat contradictions -- they are "
    "condition-dependent.\n"
    "4. End by making the GAP explicit: these reversals are not yet unified because studies differ "
    "in substrate/scale/temperature/phase and protocol; a controlled comparison (one condition "
    "varied, force field/protocol held fixed) is missing. Frame this as the open research "
    "opportunity, not a settled finding.\n"
    "5. Plain, neutral academic prose. A faithful recombinable scaffold, NOT final styled text. "
    "No invented citations, no invented numbers, no fluff."
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", nargs="*", default=None,
                    help="verify_*.json files to use (default: all in reports/connection).")
    ap.add_argument("--thesis", default=DEFAULT_THESIS)
    ap.add_argument("--slug", default="condition_dependent_reversal")
    ap.add_argument("--keep", default="conditional,real",
                    help="Verdicts to include as evidence (default conditional,real).")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    files = [Path(p) for p in args.verify] if args.verify else sorted(CONN.glob("verify_*.json"))
    keep = {k.strip() for k in args.keep.split(",") if k.strip()}
    cases, counts = load_cases(files, keep)
    if not cases:
        print(f"no usable cases (verdict counts: {counts}).")
        return 1

    packet = {"thesis": args.thesis, "verdict_counts": counts, "cases": cases}
    user = (f"THESIS to argue: {args.thesis}\n\n"
            f"VERIFIED MATERIAL (use only this; verdict_counts gives the wider sample context):\n"
            f"{json.dumps(packet, ensure_ascii=False, indent=1)}\n\nWrite the subsection now.")
    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)
    text = client.chat_text([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
        {"role": "system", "content": 'Respond with JSON: {"draft": "<markdown with [Sxx] citations>"}'},
    ])
    try:
        draft = json.loads(text).get("draft", text)
    except json.JSONDecodeError:
        draft = text

    # numeric fidelity gate: every number in the draft must appear in a fed quote.
    fed = " ".join(q["quote"] for c in cases for q in c["verified_quotes"])
    strip_cites = lambda s: re.sub(r"S\d+", "", s)
    nums = lambda s: set(re.findall(r"\d+(?:\.\d+)?", strip_cites(s)))
    leaked = sorted(nums(draft) - nums(fed), key=lambda x: (len(x), x))
    gate = ("numeric gate: all draft numbers trace to a quote ✓" if not leaked
            else f"numeric gate: {len(leaked)} number(s) NOT in any quote -> {leaked}")

    pairs = "; ".join("–".join(c["papers"]) + f"({c['verdict']})" for c in cases)
    out = CONN / f"draft_angle_{args.slug}.md"
    body = [
        f"# 综述初稿(接地·跨篇角度):{args.slug}\n",
        f"> 论点: {args.thesis}\n>\n> 证据对子: {pairs}\n>\n"
        f"> 更广抽样的判决分布: {counts}\n>\n> {gate}\n",
        "\n---\n\n## 忠实初稿(中性文风)\n\n" + draft + "\n",
    ]
    out.write_text("\n".join(body), encoding="utf-8")

    print(f"cases used={len(cases)} (verdict_counts={counts})")
    print(f"  {gate}")
    print(f"Wrote {out}\n")
    print(draft)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
