"""Spot-check the slim card's summary against the paper's own source text.

The production path trusts the slim card summary (relation judging reads it, not the
source). This is the trust-but-VERIFY half: on a SAMPLE of papers, an independent AI
pass re-reads the paper's abstract+conclusion (the source of truth) and checks each
summary finding's DIRECTION:
  - consistent : the source supports the finding's direction
  - reversed   : the source states the OPPOSITE direction  (the dangerous case)
  - unsupported: the source does not state it either way

Honest limits (I10): this is AI-checking-AI. It only NARROWS what a human must review.
Always eyeball the flagged (reversed/unsupported) findings against the printed source.

Output: reports/connection/summary_audit.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config

CONN = ROOT / "reports" / "connection"
# Read the SAME substantive sections the card was built from, else findings stated only in
# results/methods get falsely flagged "unsupported" (a checker artifact, not a real problem).
SOURCE_KINDS = {"abstract", "introduction", "methods", "results",
                "results_discussion", "discussion", "conclusion"}

SYSTEM = (
    "You verify a paper's summary against its OWN source text (abstract/conclusion). "
    "The source text is the ground truth. For each summary finding, decide:\n"
    "- consistent : the source supports the finding's direction.\n"
    "- reversed   : the source states the OPPOSITE direction (e.g. summary says X increases Y, "
    "source says X decreases Y).\n"
    "- unsupported: the source does not state this either way.\n"
    "Judge DIRECTION strictly. Do not be lenient: if unsure it is stated, use unsupported; "
    "if it points the other way, use reversed."
)

SCHEMA_HINT = (
    'Respond with JSON: {"checks":[{"finding":"<verbatim finding>","verdict":'
    '"consistent|reversed|unsupported","why":"<short reason citing the source>"}]}'
)


def source_text(pid: str, max_chars: int = 7000) -> str:
    path = ROOT / "library" / pid / "reading_blocks.json"
    try:
        blocks = json.loads(path.read_text(encoding="utf-8")).get("reading_blocks", [])
    except (OSError, json.JSONDecodeError):
        return ""
    parts = [b.get("text", "") or "" for b in blocks if b.get("section_kind") in SOURCE_KINDS]
    return " ".join(parts).strip()[:max_chars]


def load_summary(pid: str, card_name: str) -> list[str]:
    try:
        c = json.loads((ROOT / "library" / pid / card_name).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list((c.get("summary") or {}).get("main_findings") or [])


def pick_papers(args) -> list[str]:
    if args.papers:
        return [p.strip() for p in args.papers.split(",") if p.strip()]
    all_ids = sorted(d.name for d in (ROOT / "library").glob("S*") if d.is_dir())
    if args.sample and args.sample < len(all_ids):
        step = max(1, len(all_ids) // args.sample)
        return all_ids[::step][: args.sample]
    return all_ids


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--papers", default=None, help="Comma list of ids, e.g. S121,S93. Else use --sample.")
    ap.add_argument("--sample", type=int, default=10, help="Evenly sample this many cards if --papers not given.")
    ap.add_argument("--card-name", default="literature_card.json")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    client = OpenAICompatibleClient(load_ai_config(ROOT, Path(args.config) if args.config else None))
    papers = pick_papers(args)
    results, totals = {}, {"consistent": 0, "reversed": 0, "unsupported": 0}
    flagged = []

    for pid in papers:
        findings = load_summary(pid, args.card_name)
        src = source_text(pid)
        if not findings or not src:
            results[pid] = {"skipped": "no summary or no source"}
            continue
        user = (f"SOURCE (ground truth):\n{src}\n\nSUMMARY FINDINGS to check:\n"
                + "\n".join(f"- {f}" for f in findings))
        resp = client.chat_json([{"role": "system", "content": SYSTEM},
                                 {"role": "user", "content": user},
                                 {"role": "system", "content": SCHEMA_HINT}], SCHEMA_HINT)
        checks = resp.get("checks", []) if isinstance(resp, dict) else []
        results[pid] = checks
        for c in checks:
            v = c.get("verdict", "")
            if v in totals:
                totals[v] += 1
            if v in ("reversed", "unsupported"):
                flagged.append({"paper": pid, **c})
        print(f"  {pid}: " + ", ".join(f"{k}={sum(1 for c in checks if c.get('verdict')==k)}"
                                        for k in totals))

    out = {"card_name": args.card_name, "n_papers": len([p for p in results if isinstance(results[p], list)]),
           "totals": totals, "flagged": flagged, "by_paper": results}
    (CONN).mkdir(parents=True, exist_ok=True)
    (CONN / "summary_audit.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    tot = sum(totals.values())
    print(f"\nfindings checked: {tot}  consistent={totals['consistent']} "
          f"reversed={totals['reversed']} unsupported={totals['unsupported']}")
    print(f"FLAGGED for human review ({len(flagged)}):")
    for f in flagged[:20]:
        print(f"  [{f['verdict']}] {f['paper']}: {f.get('finding','')[:80]}  <- {f.get('why','')[:80]}")
    print(f"\nWrote {CONN / 'summary_audit.json'}  (human must eyeball flagged items -- I10)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
