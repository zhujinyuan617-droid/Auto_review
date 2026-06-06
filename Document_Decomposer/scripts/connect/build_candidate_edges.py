"""Step (2a) of the link network: recall candidate edges between papers.

Pure script, NO AI. Uses the unified vocabulary (reports/connection/vocabulary.json)
to map each card's tags to canonical concepts, then scores every paper pair by the
IDF-weighted sum of their shared canonical concepts. IDF down-weights hub concepts
(sharing "adsorption", df=63, is nearly free; sharing "kerogen type II-D", df=1, is
worth a lot) -- this is what stops the network from collapsing into a hairball.

Keeps only each paper's top-K neighbours, unions into an undirected candidate set,
and writes a density/degree/top-edges report so the result can be eyeballed before
any AI is spent on judging relation types.

Output:
  reports/connection/candidate_edges.json
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
import sys
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from docdecomp.connect import load_deferred

FACET_KEYS = {"topic": "domain_tags", "method": "methods", "object": "research_objects"}
# object/method overlap signals a real relationship more than a broad topic does
FACET_WEIGHT = {"topic": 0.6, "method": 0.8, "object": 1.0}


def load_paper_concepts(library_dir: Path, r2c: dict):
    """paper_id -> {facet: set(canonical concept)}"""
    out: dict[str, dict[str, set]] = {}
    deferred = load_deferred()
    for path in sorted(library_dir.glob("S*/literature_card.json")):
        if path.parent.name in deferred:
            continue
        card = json.loads(path.read_text(encoding="utf-8"))
        cl = card.get("classification", {}) or {}
        facets = {}
        for facet, key in FACET_KEYS.items():
            concepts = set()
            for tag in cl.get(key, []) or []:
                c = r2c.get(facet, {}).get(str(tag).strip().lower())
                if c:
                    concepts.add(c)
            facets[facet] = concepts
        out[path.parent.name] = facets
    return out


def compute_df(paper_concepts: dict):
    """facet -> {concept: number of papers having it}"""
    df = {f: Counter() for f in FACET_KEYS}
    for facets in paper_concepts.values():
        for facet, concepts in facets.items():
            for c in concepts:
                df[facet][c] += 1
    return df


def score_pair(a_f, b_f, df, n):
    """IDF-weighted shared-concept score + the shared concepts that drove it."""
    score = 0.0
    shared = {}
    for facet in FACET_KEYS:
        common = a_f[facet] & b_f[facet]
        if not common:
            continue
        shared[facet] = sorted(common)
        for c in common:
            idf = math.log(n / df[facet][c]) if df[facet][c] else 0.0
            score += FACET_WEIGHT[facet] * idf
    return score, shared


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--vocab", default=str(ROOT / "reports/connection/vocabulary.json"))
    ap.add_argument("--out", default=str(ROOT / "reports/connection/candidate_edges.json"))
    ap.add_argument("--top-k", type=int, default=10, help="Max neighbours kept per paper.")
    ap.add_argument("--min-score", type=float, default=0.0, help="Drop edges below this score before top-K.")
    args = ap.parse_args()

    vocab = json.loads(Path(args.vocab).read_text(encoding="utf-8"))
    r2c = vocab["raw_to_canonical"]
    paper_concepts = load_paper_concepts(Path(args.library_dir), r2c)
    papers = [p for p, f in paper_concepts.items() if any(f.values())]
    n = len(papers)
    df = compute_df({p: paper_concepts[p] for p in papers})

    # all scored pairs
    scored: dict[tuple, tuple] = {}
    for i, a in enumerate(papers):
        for b in papers[i + 1:]:
            s, shared = score_pair(paper_concepts[a], paper_concepts[b], df, n)
            if s > args.min_score and shared:
                scored[(a, b)] = (s, shared)

    # top-K neighbours per paper -> union (undirected)
    neighbours = defaultdict(list)
    for (a, b), (s, _) in scored.items():
        neighbours[a].append((s, b))
        neighbours[b].append((s, a))
    keep = set()
    for p, lst in neighbours.items():
        lst.sort(reverse=True)
        for s, q in lst[: args.top_k]:
            keep.add((p, q) if p < q else (q, p))

    edges = []
    for (a, b) in sorted(keep):
        s, shared = scored[(a, b)]
        edges.append({"a": a, "b": b, "candidate_score": round(s, 3), "shared": shared})
    edges.sort(key=lambda e: e["candidate_score"], reverse=True)

    out = {
        "n_papers": n,
        "top_k": args.top_k,
        "facet_weight": FACET_WEIGHT,
        "n_candidate_edges": len(edges),
        "edges": edges,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---- report ----
    deg = Counter()
    for e in edges:
        deg[e["a"]] += 1
        deg[e["b"]] += 1
    max_possible = n * (n - 1) // 2
    print(f"papers: {n}")
    print(f"all pairs sharing >=1 concept: {len(scored)} ({100*len(scored)/max_possible:.0f}% of {max_possible})")
    print(f"candidate edges kept (top-{args.top_k}/paper): {len(edges)} "
          f"({100*len(edges)/max_possible:.1f}% of all pairs)")
    degs = sorted(deg.values(), reverse=True)
    print(f"degree: max={degs[0]} median={degs[len(degs)//2]} min={degs[-1]} "
          f"isolated(0 edges)={n - len(deg)}")
    print(f"avg degree: {2*len(edges)/n:.1f}")
    print("\nhighest-degree papers (most connected):")
    for p, d in deg.most_common(6):
        print(f"  {p}: {d}")
    print("\n=== top 20 strongest candidate edges ===")
    for e in edges[:20]:
        sh = "; ".join(f"{f}:{'/'.join(v)}" for f, v in e["shared"].items())
        print(f"  {e['candidate_score']:5.2f}  {e['a']}-{e['b']}   [{sh}]")
    print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
