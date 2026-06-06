"""Audit how well literature-card quotes are grounded in the source reading blocks.

OBJECTIVE, mechanical, whole-library check for ISSUES.md I1 ("card quality").
NOT an LLM judging the card (that would be I10). For every evidence item in every
card (any dict carrying both `quote` and `reading_block_id`), it checks whether the
quote text actually appears in the reading block it cites.

Each quote -> one of:
  - in_cited   : appears in the reading block it cites            (good)
  - elsewhere  : not in cited block but appears in some other block (wrong id)
  - ungrounded : appears in NO reading block of that paper        (fabricated / heavily altered)

Matching is tolerant: lowercase + keep only alphanumerics (so whitespace, punctuation,
ligatures and OCR spacing like "fl uid" don't cause false misses). This measures
fabrication / wrong-source, NOT quote prettiness (mid-word truncation still counts as
grounded -- that is a separate issue).

Output: reports/connection/card_grounding_audit.json + a console summary.
Read-only over library/. No AI.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def norm(s: str) -> str:
    # letters only (drop digits too): Docling injects stray line-number digits like
    # "high pressure 9 methane" mid-sentence, which would break an alnum match even
    # though the sentence is really there. This check verifies the sentence is in the
    # source, NOT that numbers are correct (numeric correctness is a separate concern).
    return "".join(ch.lower() for ch in s if ch.isalpha())


def collect_quotes(obj, out):
    if isinstance(obj, dict):
        if "quote" in obj and "reading_block_id" in obj:
            out.append((str(obj["reading_block_id"]), str(obj["quote"])))
        for v in obj.values():
            collect_quotes(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_quotes(v, out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--out", default=str(ROOT / "reports/connection/card_grounding_audit.json"))
    ap.add_argument("--min-quote-chars", type=int, default=12,
                    help="Ignore quotes shorter than this many alnum chars (trivial matches).")
    args = ap.parse_args()

    lib = Path(args.library_dir)
    per_card = {}
    tot_q = tot_cited = tot_else = tot_ung = 0

    for cpath in sorted(lib.glob("S*/literature_card.json")):
        pid = cpath.parent.name
        rb_path = cpath.parent / "reading_blocks.json"
        if not rb_path.exists():
            continue
        blocks = json.loads(rb_path.read_text(encoding="utf-8")).get("reading_blocks", [])
        block_norm = {b.get("reading_block_id", ""): norm(b.get("text", "") or "") for b in blocks}
        all_norm = "".join(block_norm.values())

        card = json.loads(cpath.read_text(encoding="utf-8"))
        quotes = []
        collect_quotes(card, quotes)

        n_q = n_cited = n_else = n_ung = 0
        bad = []
        for rb_id, quote in quotes:
            # AI sometimes splices non-contiguous spans with "..."; check each fragment.
            raw_frags = quote.replace("…", "...").split("...")
            frags = [norm(f) for f in raw_frags]
            frags = [f for f in frags if len(f) >= args.min_quote_chars]
            if not frags:
                continue
            n_q += 1
            cited_txt = block_norm.get(rb_id, "")
            if all(f in cited_txt for f in frags):
                n_cited += 1
            elif all(f in all_norm for f in frags):
                n_else += 1
                bad.append({"type": "wrong_block_or_spliced", "cited": rb_id, "quote": quote[:90]})
            else:
                n_ung += 1
                bad.append({"type": "ungrounded", "cited": rb_id, "quote": quote[:110]})

        cls = card.get("classification") or {}
        flags = []
        if not (card.get("study_design") or []):
            flags.append("study_design_empty")
        if not any(cls.get(k) for k in ("domain_tags", "methods", "research_objects")):
            flags.append("classification_empty")

        per_card[pid] = {
            "n_quotes": n_q, "in_cited": n_cited, "elsewhere": n_else, "ungrounded": n_ung,
            "grounded_rate": round(n_cited / n_q, 3) if n_q else None,
            "flags": flags, "bad_examples": bad[:5],
        }
        tot_q += n_q; tot_cited += n_cited; tot_else += n_else; tot_ung += n_ung

    out = {
        "n_cards": len(per_card),
        "total_quotes": tot_q,
        "in_cited": tot_cited, "elsewhere": tot_else, "ungrounded": tot_ung,
        "overall_grounded_rate": round(tot_cited / tot_q, 3) if tot_q else None,
        "per_card": per_card,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"cards: {len(per_card)}   quotes checked: {tot_q}")
    print(f"  in cited block : {tot_cited} ({100*tot_cited/tot_q:.1f}%)")
    print(f"  wrong block    : {tot_else} ({100*tot_else/tot_q:.1f}%)")
    print(f"  UNGROUNDED     : {tot_ung} ({100*tot_ung/tot_q:.1f}%)  <- not in any block of that paper")
    rates = [(d["grounded_rate"], p) for p, d in per_card.items() if d["grounded_rate"] is not None]
    rates.sort()
    print(f"\nworst 12 cards by grounded_rate:")
    for r, p in rates[:12]:
        d = per_card[p]
        print(f"  {p}: {r:.2f}  (q={d['n_quotes']} cited={d['in_cited']} else={d['elsewhere']} ung={d['ungrounded']}) {d['flags']}")
    empty_sd = [p for p, d in per_card.items() if "study_design_empty" in d["flags"]]
    empty_cls = [p for p, d in per_card.items() if "classification_empty" in d["flags"]]
    print(f"\nstudy_design empty: {len(empty_sd)} cards {sorted(empty_sd)[:20]}")
    print(f"classification empty: {len(empty_cls)} cards {sorted(empty_cls)}")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
