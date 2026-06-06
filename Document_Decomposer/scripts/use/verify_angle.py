"""Step 3 of interrogation: an AI verifier that reads the SOURCE and judges an angle.

Workflow: propose_angles (AI finds angles) -> query_network (plain, locates papers)
-> THIS (AI reads each paper's own passages and judges whether the flagged
relation is real). Honest about the S121-S93 lesson: a flagged "contradiction" may
actually be agreement or merely conditional, so the verifier is told to DISTRUST the
flag and judge only from the passages. Output is still AI -- a human adjudicates (I10).

Plain retrieval (no AI) pulls the relevant sentences; DeepSeek does the judging.

Output: reports/connection/verify_<papers>.json
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
SKIP_SECTIONS = {"references", "acknowledgements", "front_matter", "keywords"}

SYSTEM = (
    "You verify whether a claimed relation between papers is real, judging ONLY from each "
    "paper's own passages provided. DISTRUST the claim/flag -- it may be wrong. A flagged "
    "'contradiction' is often actually: (a) real, (b) FALSE (the papers actually agree), or "
    "(c) CONDITIONAL (both true, but they differ because of some variable like wettability, "
    "pore size, pressure, method). If conditional, NAME the reconciling variable and cite the "
    "passages showing each paper's condition. Quote the exact sentence from each paper that "
    "supports your verdict. If the passages do not actually conflict, say FALSE. Do not invent."
)

SCHEMA_HINT = (
    'Respond with JSON: {"verdict":"real|false|conditional","reconciling_variable":"<or null>",'
    '"per_paper":[{"id":"Sxx","stance":"<one line>","quote":"<verbatim sentence>"}],'
    '"explanation":"<2-3 sentences>"}'
)


# words that signal a FINDING/direction -- these sentences matter most for judging a relation
DIRECTION_WORDS = (
    "increase", "increased", "increases", "increasing", "enhance", "enhanced", "improv",
    "higher", "greater", "more ", "stronger", "rise", "raised", "promot",
    "decrease", "decreased", "decreases", "decreasing", "reduce", "reduced", "reduces",
    "lower", "less ", "weaker", "suppress", "drop", "decline", "hinder",
)
HIGH_VALUE_SECTIONS = {"abstract", "conclusion", "results_discussion", "discussion"}


def passages(pid: str, terms: list[str], max_sent: int = 18, max_chars: int = 4000) -> list[str]:
    """Plain retrieval. Prioritise sentences that carry a DIRECTION/finding and that live in
    abstract/conclusion/discussion, so the key conclusion is not truncated away (the bug that
    made the S08 vug verdict wrong)."""
    path = ROOT / "library" / pid / "reading_blocks.json"
    try:
        blocks = json.loads(path.read_text(encoding="utf-8")).get("reading_blocks", [])
    except (OSError, json.JSONDecodeError):
        return []
    terms_l = [t.lower() for t in terms]
    cand, seen = [], set()
    for order, b in enumerate(blocks):
        if b.get("section_kind") in SKIP_SECTIONS:
            continue
        sec = b.get("section_kind", "")
        for s in re.split(r"(?<=[.]) ", b.get("text", "") or ""):
            sl = s.lower()
            if not any(t in sl for t in terms_l):
                continue
            key = s.strip()[:50]
            if key in seen:
                continue
            seen.add(key)
            score = (2 if any(w in sl for w in DIRECTION_WORDS) else 0) + (1 if sec in HIGH_VALUE_SECTIONS else 0)
            cand.append((score, order, sec, s.strip()[:300]))
    # keep the highest-value sentences, then show them in document order
    cand.sort(key=lambda c: c[0], reverse=True)
    kept = cand[:max_sent]
    kept.sort(key=lambda c: c[1])
    out, total = [], 0
    for _, _, sec, snip in kept:
        out.append(f"«{sec}» {snip}")
        total += len(snip)
        if total >= max_chars:
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--papers", required=True, help="Comma list, e.g. S08,S28")
    ap.add_argument("--terms", required=True, help="Comma list of terms to pull passages on, e.g. vug,sweep")
    ap.add_argument("--claim", default="", help="The claimed relation/thesis to test (context only).")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    pids = [p.strip() for p in args.papers.split(",") if p.strip()]
    terms = [t.strip() for t in args.terms.split(",") if t.strip()]
    blocks = []
    for pid in pids:
        ps = passages(pid, terms)
        blocks.append(f"===== {pid} (its own passages on: {', '.join(terms)}) =====\n"
                      + ("\n".join(ps) if ps else "(no matching passages found)"))
    user = (
        (f"CLAIMED relation to test (DISTRUST it): {args.claim}\n\n" if args.claim else "")
        + "Judge ONLY from these passages:\n\n" + "\n\n".join(blocks)
    )
    client = OpenAICompatibleClient(load_ai_config(ROOT, Path(args.config) if args.config else None))
    resp = client.chat_json([{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": user},
                             {"role": "system", "content": SCHEMA_HINT}], SCHEMA_HINT)

    out = CONN / f"verify_{'_'.join(pids)}.json"
    out.write_text(json.dumps(resp, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERDICT: {resp.get('verdict')}   reconciling_variable: {resp.get('reconciling_variable')}")
    for pp in resp.get("per_paper", []):
        print(f"  [{pp.get('id')}] {pp.get('stance','')}")
        print(f"      \"{pp.get('quote','')[:160]}\"")
    print(f"explanation: {resp.get('explanation','')}")
    print(f"\nWrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
