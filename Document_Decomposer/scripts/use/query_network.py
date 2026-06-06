"""Query the connection network -- the first 'use' of the assembled layers.

Two modes, both grounded in the built artifacts (edges.json + concept_index.json
+ literature cards); nothing is invented:

  --concept "capillary condensation"
      Around a thesis concept: which papers study it centrally, which only mention
      it in passing (with the quote), and the typed relations (supports / contradicts
      / complements) that already exist among those papers. This is the raw material
      for a review section on that concept.

  --paper S18
      For one paper: its typed neighbours grouped by relation (with the AI rationale),
      and which concepts it is central / passing on.

Read-only. No AI. This is the seam the drafting layer will eventually sit on.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONN = ROOT / "reports" / "connection"


def load():
    edges = json.loads((CONN / "edges.json").read_text(encoding="utf-8"))["edges"]
    cidx = json.loads((CONN / "concept_index.json").read_text(encoding="utf-8"))["concepts"]
    titles = {}
    for p in (ROOT / "library").glob("S*/literature_card.json"):
        c = json.loads(p.read_text(encoding="utf-8"))
        titles[p.parent.name] = (c.get("paper", {}) or {}).get("title", "")
    return edges, cidx, titles


def t(titles, pid):
    return f"{pid} · {titles.get(pid,'')[:70]}"


def query_concept(concept, edges, cidx, titles):
    if concept not in cidx:
        near = [c for c in cidx if concept.lower() in c.lower()]
        print(f"概念 '{concept}' 不在索引。" + (f" 近似: {near[:8]}" if near else ""))
        return
    d = cidx[concept]
    members = set(d["central"]) | {p["paper"] for p in d["passing"]}
    print(f"### 围绕「{concept}」  (facets: {','.join(d['facets'])})\n")
    print(f"■ 中心研究 {d['n_central']} 篇:")
    for p in d["central"]:
        print(f"   - {t(titles, p)}")
    print(f"\n■ 一笔带过 {d['n_passing']} 篇 (作者没当重点、卡片里没有):")
    for p in d["passing"][:12]:
        print(f"   - {t(titles, p['paper'])}  «{p['section']}»")
        print(f"       \"...{p['snippet'][:130]}...\"")
    if d["n_passing"] > 12:
        print(f"   ... 还有 {d['n_passing']-12} 篇")
    # typed relations among the papers touching this concept
    rel = defaultdict(list)
    for e in edges:
        if e["a"] in members and e["b"] in members:
            rel[e["relation"]].append(e)
    print(f"\n■ 这些论文之间已有的关系 (来自关联网):")
    for r in ["contradicts", "complements", "supports"]:
        es = rel.get(r, [])
        if not es:
            continue
        print(f"   [{r}] {len(es)} 条:")
        for e in es[:6]:
            print(f"      {e['a']}-{e['b']}: {e['rationale'][:100]}")


def query_paper(pid, edges, cidx, titles):
    print(f"### {t(titles, pid)}\n")
    rel = defaultdict(list)
    for e in edges:
        if e["a"] == pid or e["b"] == pid:
            other = e["b"] if e["a"] == pid else e["a"]
            rel[e["relation"]].append((other, e))
    print("■ 关联网里的邻居 (按关系):")
    for r in ["contradicts", "complements", "supports"]:
        es = rel.get(r, [])
        if not es:
            continue
        print(f"   [{r}] {len(es)}:")
        for other, e in es[:8]:
            print(f"      {other}: {e['rationale'][:100]}")
    central = sorted(c for c, d in cidx.items() if pid in d["central"])
    passing = sorted(c for c, d in cidx.items() if any(p["paper"] == pid for p in d["passing"]))
    print(f"\n■ 本篇中心概念 ({len(central)}): {', '.join(central[:20])}")
    print(f"■ 本篇一笔带过的概念 ({len(passing)}): {', '.join(passing[:25])}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--concept", default=None)
    ap.add_argument("--paper", default=None)
    args = ap.parse_args()
    edges, cidx, titles = load()
    if args.concept:
        query_concept(args.concept, edges, cidx, titles)
    elif args.paper:
        query_paper(args.paper, edges, cidx, titles)
    else:
        print("用 --concept \"<概念>\" 或 --paper Sxx")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
