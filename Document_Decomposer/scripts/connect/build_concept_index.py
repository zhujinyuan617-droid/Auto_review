"""Step (3) of the route: concept -> passage index with prominence.

Answers the "passing mention" problem: a concept an author mentions only in passing
(so it never reached that paper's literature card) but which is central elsewhere -- or
which, scattered across many papers as a side note, marks an under-studied gap.

For every canonical concept in the unified vocabulary (reports/connection/vocabulary.json)
we scan the FULL reading_blocks text of every paper for any of its surface forms, then
split the papers that mention it into:
  - central : the concept reached the paper's literature card (author foregrounded it)
  - passing : it only appears in the body text, not the card

Pure script, no AI. Lexical matching, so single generic words ("water", "coal") are noisy
-- specific multi-word concepts ("knudsen diffusion", "capillary condensation") are where
the signal is. Match counts are reported so the noise is visible, not hidden.

Output: reports/connection/concept_index.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from docdecomp.connect import load_deferred
CONN = ROOT / "reports" / "connection"
FACET_KEYS = {"topic": "domain_tags", "method": "methods", "object": "research_objects"}

# Generic terms that are not specific research targets -- excluded from the
# "research gap" ranking (they are kept in the index, just not ranked as gaps).
GENERIC = {
    "energy", "experimental", "experiment", "water", "pores", "pore", "flow",
    "storage", "gases", "gas", "review", "transport", "shale", "methane", "coal",
    "natural gas", "organic matter", "permeability", "porous media", "micropores",
    "pore structure", "numerical simulation", "simulation", "diffusion",
    "adsorption", "desorption", "temperature", "pressure", "density", "molecular",
    "molecular dynamics", "molecular simulation", "carbon dioxide", "nanopores",
    "porous materials", "fluid", "fluids", "petroleum engineering", "hydrocarbons",
    "shale gas", "experimental characterization", "modeling", "characterization",
}


def is_specific(canonical: str) -> bool:
    """A concept worth ranking as a potential gap: multi-word or a long technical
    single word, and not in the generic stoplist."""
    if canonical in GENERIC:
        return False
    return (" " in canonical) or len(canonical) >= 8


def load_vocab(vocab_path: Path):
    v = json.loads(vocab_path.read_text(encoding="utf-8"))
    # canonical -> set(member surface forms), and canonical -> facets
    members = defaultdict(set)
    facets = defaultdict(set)
    for facet, fdata in v["facets"].items():
        for con in fdata["concepts"]:
            can = con["canonical"]
            facets[can].add(facet)
            for m in con["members"]:
                members[can].add(m)
    return members, facets


def card_concepts(library_dir: Path, r2c: dict):
    """paper -> set(canonical) the author foregrounded (came from the card tags)."""
    out = defaultdict(set)
    deferred = load_deferred()
    for path in library_dir.glob("S*/literature_card.json"):
        if path.parent.name in deferred:
            continue
        c = json.loads(path.read_text(encoding="utf-8"))
        cl = c.get("classification", {}) or {}
        for facet, key in FACET_KEYS.items():
            for tag in cl.get(key, []) or []:
                can = r2c.get(facet, {}).get(str(tag).strip().lower())
                if can:
                    out[path.parent.name].add(can)
    return out


def build_matcher(members):
    """One master regex; returns (compiled, surface->canonical).

    Precision-first: only match a member that is multi-word OR equal to its canonical.
    This drops generic single-word synonyms (e.g. 'condensation' standing in for
    'capillary condensation') that cause false positives. Costs some recall on
    abbreviations -- the recall gap is the job of a later embedding/AI pass.
    """
    surf2can = {}
    for can, surfs in members.items():
        for s in surfs:
            if (" " in s) or (s == can):
                surf2can.setdefault(s, can)
    # longest first so multi-word phrases win over their substrings
    ordered = sorted(surf2can, key=len, reverse=True)
    alt = "|".join(re.escape(s) for s in ordered)
    pattern = re.compile(r"(?<![a-z])(" + alt + r")(?![a-z])", re.IGNORECASE)
    return pattern, surf2can


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--vocab", default=str(CONN / "vocabulary.json"))
    ap.add_argument("--out", default=str(CONN / "concept_index.json"))
    ap.add_argument("--snippet-chars", type=int, default=160)
    args = ap.parse_args()

    vocab = json.loads(Path(args.vocab).read_text(encoding="utf-8"))
    members, facets = load_vocab(Path(args.vocab))
    central = card_concepts(Path(args.library_dir), vocab["raw_to_canonical"])
    pattern, surf2can = build_matcher(members)

    # concept -> paper -> list of mentions(block,section,snippet)
    mentions = defaultdict(lambda: defaultdict(list))
    n_papers = 0
    deferred_main = load_deferred()
    for path in sorted(Path(args.library_dir).glob("S*/reading_blocks.json")):
        pid = path.parent.name
        if pid in deferred_main:
            continue
        n_papers += 1
        blocks = json.loads(path.read_text(encoding="utf-8")).get("reading_blocks", [])
        for b in blocks:
            # skip citation lists: matches there are reference titles, not real mentions
            if b.get("section_kind") == "references" or b.get("reading_type") == "reference_entry":
                continue
            text = b.get("text") or ""
            if not text:
                continue
            low = text.lower()
            seen_here = set()
            for m in pattern.finditer(low):
                can = surf2can.get(m.group(1).lower())
                if not can or can in seen_here:
                    continue
                seen_here.add(can)
                i = m.start()
                snip = text[max(0, i - 40): i + args.snippet_chars].strip().replace("\n", " ")
                mentions[can][pid].append({
                    "block": b.get("reading_block_id", ""),
                    "section": b.get("section_kind", ""),
                    "snippet": snip,
                })

    concepts_out = {}
    for can in sorted(members):
        papers = mentions.get(can, {})
        central_papers = sorted(p for p in papers if can in central.get(p, set()))
        # also include central papers that the lexical scan missed (card said so)
        for p, cans in central.items():
            if can in cans and p not in central_papers:
                central_papers.append(p)
        central_papers = sorted(set(central_papers))
        passing = []
        for p in sorted(papers):
            if can in central.get(p, set()):
                continue
            first = papers[p][0]
            passing.append({"paper": p, "n_hits": len(papers[p]), **first})
        if not central_papers and not passing:
            continue
        # verbatim block snippets for central papers too, so drafting can pull facts from
        # the source (slim cards no longer carry quotes). Empty if the term isn't lexically
        # in that paper's body (tag present but wording differs).
        central_evidence = []
        for p in central_papers:
            if papers.get(p):
                first = papers[p][0]
                central_evidence.append({"paper": p, "n_hits": len(papers[p]), **first})
        concepts_out[can] = {
            "facets": sorted(facets[can]),
            "members": sorted(members[can]),
            "specific": is_specific(can),
            "central": central_papers,
            "n_central": len(central_papers),
            "central_evidence": central_evidence,
            "passing": passing,
            "n_passing": len(passing),
            # invoked widely in passing but studied centrally by few = candidate gap
            "gap_score": round(len(passing) / (1 + len(central_papers)), 2),
        }

    out = {"n_papers": n_papers, "n_concepts": len(concepts_out), "concepts": concepts_out}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- report ----
    print(f"papers scanned: {n_papers}; concepts indexed: {len(concepts_out)}")
    print("\n=== candidate RESEARCH GAPS (specific concept, studied by few, invoked in passing by many) ===")
    gaps = [(c, d) for c, d in concepts_out.items()
            if d["specific"] and d["n_central"] >= 1 and d["n_passing"] >= 4]
    gaps.sort(key=lambda kv: kv[1]["gap_score"], reverse=True)
    print(f"  {'concept':30s} central passing  gap")
    for can, d in gaps[:20]:
        print(f"  {can[:30]:30s} {d['n_central']:6d} {d['n_passing']:7d} {d['gap_score']:5.1f}")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
