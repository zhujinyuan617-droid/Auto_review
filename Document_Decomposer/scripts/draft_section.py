"""Grounded drafting -- first cut, style-agnostic (the route's terminal capability).

Given a thesis concept, it assembles ONLY material already in the network
(central papers' card findings, passing-mention quotes, and the typed
supports/contradicts/complements relations among them) and asks the AI to write a
traceable review subsection: every claim cited [Sxx], agreements/tensions/gaps made
explicit, passing-only evidence flagged, no invented numbers.

This is deliberately NOT yet in the user's writing style -- that needs a style corpus
of the user's past papers (open dependency). It produces a faithful, recombinable
draft now; style is a later pass.

Output: reports/connection/draft_<concept>.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config

CONN = ROOT / "reports" / "connection"


def card_findings(pid):
    c = json.loads((ROOT / "library" / pid / "literature_card.json").read_text(encoding="utf-8"))
    kfs = []
    for kf in (c.get("key_findings") or [])[:5]:
        x = kf.get("claim") or kf.get("finding") or kf.get("detail") or ""
        if x:
            kfs.append(x)
    return (c.get("paper", {}) or {}).get("title", ""), kfs


def build_packet(concept, edges, cidx):
    d = cidx[concept]
    members = set(d["central"]) | {p["paper"] for p in d["passing"]}
    central = []
    for p in d["central"]:
        title, kfs = card_findings(p)
        central.append({"id": p, "title": title, "findings": kfs})
    passing = [{"id": p["paper"], "section": p["section"], "quote": p["snippet"]} for p in d["passing"]]
    rels = defaultdict(list)
    for e in edges:
        if e["a"] in members and e["b"] in members:
            rels[e["relation"]].append({"a": e["a"], "b": e["b"], "why": e["rationale"]})
    return {"concept": concept, "central": central, "passing": passing, "relations": dict(rels)}


SYSTEM = (
    "You are drafting one subsection of a literature review, grounded ONLY in the "
    "provided material. Rules:\n"
    "1. Use ONLY the supplied papers, findings, quotes and relations. Invent nothing; "
    "add no numbers that are not in the material.\n"
    "2. Cite every claim with the paper id in brackets, e.g. [S18]. Multiple: [S18; S33].\n"
    "3. Make the structure of the evidence explicit: where papers agree (supports), where "
    "they conflict (contradicts), and where they cover complementary pieces (complements).\n"
    "4. When a point rests only on a passing mention, say so (e.g. 'noted in passing by [Sxx]').\n"
    "5. Plain, neutral academic prose. No invented citations, no fluff. This is a faithful "
    "scaffold, not the final styled text."
)

# Pass 2: re-style the faithful draft into the target author's voice WITHOUT touching facts.
STYLE_SYSTEM = (
    "You rewrite a review subsection to match the AUTHOR's writing style shown in the samples "
    "(sentence rhythm, connectives, hedging, paragraph habits, how they foreground claims).\n"
    "HARD CONSTRAINTS -- violating any is failure:\n"
    "1. Keep EVERY [Sxx] citation, attached to the same claim. Do not add or remove citations.\n"
    "2. Do not add, drop, or change any factual claim, number, unit, or qualifier.\n"
    "3. Do not introduce any fact not already in the draft.\n"
    "Only change voice, phrasing, transitions and flow. Same facts, same citations, new style."
)


def load_style(args):
    """Return (style_text, label). --style-corpus = user's own writing (file or dir).
    --style-paper Sxx = a library paper's prose as a clearly-labelled STAND-IN for demos."""
    if args.style_corpus:
        p = Path(args.style_corpus)
        texts = []
        files = sorted(p.glob("*")) if p.is_dir() else [p]
        for f in files:
            if f.suffix.lower() in {".md", ".txt"}:
                texts.append(f.read_text(encoding="utf-8"))
        return ("\n\n".join(texts)[:6000], f"user corpus: {args.style_corpus}")
    if args.style_paper:
        rb = json.loads((ROOT / "library" / args.style_paper / "reading_blocks.json").read_text(encoding="utf-8"))
        paras = [b.get("text", "") for b in rb.get("reading_blocks", [])
                 if b.get("reading_type") == "paragraph" and b.get("section_kind") not in {"references", "abstract"}]
        return ("\n\n".join(paras)[:6000], f"STAND-IN (library paper {args.style_paper}'s prose)")
    return (None, None)


def restyle(client, draft, style_text):
    text = client.chat_text([
        {"role": "system", "content": STYLE_SYSTEM},
        {"role": "user", "content": f"AUTHOR STYLE SAMPLES:\n{style_text}\n\nDRAFT TO RESTYLE (keep all [Sxx] and all facts):\n{draft}"},
        {"role": "system", "content": 'Respond with JSON: {"draft": "<restyled markdown, all [Sxx] preserved>"}'},
    ])
    try:
        return json.loads(text).get("draft", text)
    except json.JSONDecodeError:
        return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--concept", required=True)
    ap.add_argument("--config", default=None)
    ap.add_argument("--style-corpus", default=None, help="File or dir of the user's own writing (target style).")
    ap.add_argument("--style-paper", default=None, help="Sxx: use a library paper's prose as a STAND-IN style (demo only).")
    args = ap.parse_args()

    edges = json.loads((CONN / "edges.json").read_text(encoding="utf-8"))["edges"]
    cidx = json.loads((CONN / "concept_index.json").read_text(encoding="utf-8"))["concepts"]
    if args.concept not in cidx:
        near = [c for c in cidx if args.concept.lower() in c.lower()]
        print(f"'{args.concept}' not indexed." + (f" near: {near[:8]}" if near else ""))
        return 1

    packet = build_packet(args.concept, edges, cidx)
    user = (
        f"Thesis concept: {args.concept}\n\n"
        f"MATERIAL (use only this):\n{json.dumps(packet, ensure_ascii=False, indent=1)}\n\n"
        "Write the review subsection now."
    )
    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)
    text = client.chat_text([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
        {"role": "system", "content": 'Respond with JSON: {"draft": "<markdown text with [Sxx] citations>"}'},
    ])
    try:
        draft = json.loads(text).get("draft", text)
    except json.JSONDecodeError:
        draft = text

    # optional pass 2: re-style into target author voice, facts/citations frozen
    style_text, style_label = load_style(args)
    styled = None
    fidelity = ""
    if style_text:
        styled = restyle(client, draft, style_text)
        import re
        cites = lambda s: set(re.findall(r"\[(S\d+)", s)) | set(re.findall(r";\s*(S\d+)", s))
        nums = lambda s: set(re.findall(r"\d+(?:\.\d+)?", s))
        c0, c1 = cites(draft), cites(styled)
        n0, n1 = nums(draft), nums(styled)
        fidelity = (f"citations faithful={c0 == c1} (lost={sorted(c0 - c1)} added={sorted(c1 - c0)}); "
                    f"no new numbers={n1 <= n0} (added={sorted(n1 - n0)})")

    safe = args.concept.replace(" ", "_").replace("/", "-")
    out = CONN / f"draft_{safe}.md"
    cites_central = ", ".join(c["id"] for c in packet["central"])
    cites_passing = ", ".join(p["id"] for p in packet["passing"])
    body = [
        f"# 综述初稿(接地):{args.concept}\n",
        f"> 素材来源 — 中心研究: {cites_central}\n>\n> 一笔带过: {cites_passing}\n",
        "\n---\n\n## 忠实初稿(中性文风)\n\n" + draft + "\n",
    ]
    if styled:
        body.append(f"\n---\n\n## 风格化稿(目标风格 = {style_label})\n\n> 保真校验: {fidelity}\n\n" + styled + "\n")
    out.write_text("\n".join(body), encoding="utf-8")

    print(f"central={len(packet['central'])} passing={len(packet['passing'])} "
          f"relations={ {k: len(v) for k, v in packet['relations'].items()} }")
    if styled:
        print(f"style pass: {style_label}\n  {fidelity}")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
