"""Ideation layer (step ④): propose grounded review angles for the user to interrogate.

This serves the terminal-state clause '用户与 AI 就关键论点达成一致后' -- before drafting,
the AI must surface candidate theses the user can question and agree on. Every angle is
grounded in real network structure (no web search, no invention):

  - TENSION angles   : from contradicts edges (unresolved disagreements = high-value reviews)
  - GAP angles       : from concept_index gap ranking (studied by few, invoked by many)
  - SYNTHESIS angles : from concepts whose papers are richly linked by complements edges

The AI only phrases/ranks these candidates and must cite [Sxx]; it adds no facts.
Read-only over edges.json + concept_index.json. Output: reports/connection/angles.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config

CONN = ROOT / "reports" / "connection"


def build_candidates(edges, cidx, n_each=10):
    # tension: contradicts edges
    tension = [{"a": e["a"], "b": e["b"], "shared": e["shared"], "why": e["rationale"]}
               for e in edges if e["relation"] == "contradicts"]

    # gaps: specific concepts, few central, many passing
    gaps = [{"concept": c, "n_central": d["n_central"], "n_passing": d["n_passing"],
             "central": d["central"], "gap_score": d["gap_score"]}
            for c, d in cidx.items()
            if d.get("specific") and d["n_central"] >= 1 and d["n_passing"] >= 5]
    gaps.sort(key=lambda x: x["gap_score"], reverse=True)
    gaps = gaps[:n_each]

    # synthesis: concepts whose papers are richly connected by complements
    comp_by_concept = defaultdict(int)
    member_index = {}
    for c, d in cidx.items():
        member_index[c] = set(d["central"]) | {p["paper"] for p in d["passing"]}
    for e in edges:
        if e["relation"] != "complements":
            continue
        for c, members in member_index.items():
            if e["a"] in members and e["b"] in members:
                comp_by_concept[c] += 1
    synth = []
    for c, n in sorted(comp_by_concept.items(), key=lambda x: x[1], reverse=True):
        d = cidx[c]
        if not d.get("specific") or d["n_central"] < 2:
            continue
        synth.append({"concept": c, "n_complements": n,
                      "central": d["central"][:8], "n_central": d["n_central"]})
        if len(synth) >= n_each:
            break
    return {"tension": tension, "gaps": gaps, "synthesis": synth}


SYSTEM = (
    "You select the FEW BEST candidate review angles (theses) an author could actually write, "
    "grounded ONLY in the supplied network structure (real contradicts edges, gap rankings, "
    "complement clusters).\n"
    "PRIORITY ORDER: (1) UNRESOLVED CONTRADICTIONS — papers genuinely disagree on a SPECIFIC "
    "point; (2) ACTIONABLE GAPS — a specific concept widely invoked but studied by few, could be "
    "its own study; (3) NEW-FRAMEWORK SYNTHESIS — scattered results that COMBINE into a "
    "non-obvious unifying framework.\n"
    "EVERY angle MUST be:\n"
    "- NON-OBVIOUS: not a textbook fact or settled consensus;\n"
    "- SPECIFIC & ACTIONABLE: name the exact disagreement/gap and land on a concrete research "
    "question; never 'more research is needed on X';\n"
    "- GENUINELY OPEN: still debated or unfilled, not already resolved;\n"
    "- GROUNDED: cite >=2 papers by id and say what each contributes; a single-paper angle is "
    "allowed ONLY for a strong gap (one central paper + many passing mentions).\n"
    "HARD EXCLUSIONS — never output:\n"
    "- that a method/tool is popular or 'the method of choice' (a fact, not an angle);\n"
    "- mere summaries / 'trends are consistent across studies' with no tension and no new framework;\n"
    "- vague, broad, or textbook claims.\n"
    "For each KEPT angle give: thesis (one line); type (contradiction/gap/synthesis); papers [Sxx]; "
    "why (the specific disagreement/gap/framework); decide (the concrete research question AND what "
    "evidence would settle it). Prefer FEW SHARP angles over many — drop anything that does not "
    "clear the bar. Invent no facts and no papers; cite only ids present in the material."
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=None)
    ap.add_argument("--n", type=int, default=6, help="How many angles to propose.")
    args = ap.parse_args()

    edges = json.loads((CONN / "edges.json").read_text(encoding="utf-8"))["edges"]
    cidx = json.loads((CONN / "concept_index.json").read_text(encoding="utf-8"))["concepts"]
    cand = build_candidates(edges, cidx)

    user = (
        f"Propose {args.n} grounded review angles. Cover a mix of tension, gap, and synthesis.\n\n"
        f"NETWORK STRUCTURE (use only this):\n{json.dumps(cand, ensure_ascii=False, indent=1)}"
    )
    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)
    text = client.chat_text([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
        {"role": "system", "content": 'Respond with JSON: {"angles":[{"thesis","type","papers":["Sxx"],"why","decide"}]}'},
    ])
    try:
        angles = json.loads(text).get("angles", [])
    except json.JSONDecodeError:
        angles = []

    lines = ["# 候选综述角度(接地·供追问)\n",
             f"> 来自 {len(edges)} 条关系边 + {len(cidx)} 个概念的真实结构;每个角度可 drill-down 到原文。\n"]
    for i, a in enumerate(angles, 1):
        papers = ", ".join(a.get("papers", []))
        lines.append(f"\n## 角度 {i} · [{a.get('type','')}] {a.get('thesis','')}\n")
        lines.append(f"- **为何值得写**: {a.get('why','')}")
        lines.append(f"- **关键论文**: {papers}")
        lines.append(f"- **你需要先定**: {a.get('decide','')}")
    out = CONN / "angles.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"candidates: tension={len(cand['tension'])} gaps={len(cand['gaps'])} synthesis={len(cand['synthesis'])}")
    print(f"proposed {len(angles)} angles -> {out}\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
