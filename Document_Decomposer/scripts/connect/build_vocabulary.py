"""Build a unified controlled vocabulary from literature-card tags.

Step (1) of the cross-paper link-network route. Reads every
library/Sxx/literature_card.json, collects the free-text tags from
classification.{domain_tags, methods, research_objects}, and asks the AI to
collapse the many surface forms into a small set of canonical concepts per
facet (synonym normalization only -- it must NOT invent concepts or merge
genuinely different ones).

Output: reports/connection/vocabulary.json
  {
    "facets": {
      "topic":  {"concepts": [{"canonical","members":[...],"card_count"}], ...},
      "method": {...},
      "object": {...}
    },
    "raw_to_canonical": {"topic": {"shale gas recovery": "shale gas", ...}, ...}
  }

This is a coarse, "direction-level" artifact: wording drift here is tolerable
because it only seeds candidate links; precise facts live in the atoms layer.
Regenerating is safe -- it touches no existing data, only this one file.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config
from docdecomp.connect import load_deferred

# facet name -> classification key in the literature card
FACET_KEYS = {
    "topic": "domain_tags",
    "method": "methods",
    "object": "research_objects",
}

SYSTEM = (
    "You normalize a messy list of free-text research tags into a controlled vocabulary by "
    "grouping ONLY different surface forms of the SAME concept.\n"
    "MERGE ONLY: spelling/plural/abbreviation variants and exact synonyms — e.g. "
    "'gcmc'='grand canonical monte carlo', 'co2'='carbon dioxide', "
    "'shale gas recovery' under 'shale gas'.\n"
    "DO NOT MERGE two DIFFERENT phenomena, mechanisms, methods, or materials, even if they are "
    "related or in the same field. Keep separate, for example: 'capillary condensation' vs "
    "'phase behavior'; 'diffusion' vs 'fluid dynamics' vs 'transport'; 'knudsen diffusion' vs "
    "'diffusion'; 'clay minerals' vs 'kerogen'.\n"
    "NEVER create broad umbrella / grab-bag concepts (e.g. 'fluid dynamics', 'materials', "
    "'environmental', 'energy') that swallow several distinct topics.\n"
    "When unsure whether two tags are the same concept, KEEP THEM SEPARATE. Prefer MANY "
    "fine-grained concepts over few broad ones. A group should rarely exceed ~8 members unless "
    "they are clearly the same term spelled differently.\n"
    "Prefer the most common, concise, widely-recognized surface form as the canonical name. "
    "Every input tag must appear in exactly one group."
)


def collect_tags(library_dir: Path):
    """Return {facet: Counter(raw_tag -> card_count)} and per-facet card sets."""
    counts = {f: Counter() for f in FACET_KEYS}
    deferred = load_deferred()
    cards = [c for c in sorted(library_dir.glob("S*/literature_card.json")) if c.parent.name not in deferred]
    for path in cards:
        try:
            card = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        classification = card.get("classification") or {}
        for facet, key in FACET_KEYS.items():
            seen = set()
            for tag in classification.get(key, []) or []:
                norm = str(tag).strip().lower()
                if norm and norm not in seen:
                    seen.add(norm)
                    counts[facet][norm] += 1
    return counts, len(cards)


def build_prompt(facet: str, counts: Counter) -> list[dict[str, str]]:
    items = [{"tag": t, "card_count": c} for t, c in counts.most_common()]
    user = (
        f"Facet: {facet}\n"
        f"Here are {len(items)} raw tags with how many papers use each. "
        "Group synonymous / near-duplicate surface forms into canonical "
        "concepts. Keep distinct concepts distinct.\n\n"
        f"{json.dumps(items, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


SCHEMA_HINT = (
    'Respond with a single JSON object: '
    '{"concepts": [{"canonical": "<name>", "members": ["<raw tag>", ...]}]}. '
    "Every input tag must appear in exactly one members list. "
    "Use lowercase canonical names."
)


def normalize_facet(client, facet: str, counts: Counter) -> dict:
    response = client.chat_json(build_prompt(facet, counts), SCHEMA_HINT)
    concepts = response.get("concepts") or []
    raw_to_canonical: dict[str, str] = {}
    out_concepts = []
    covered = set()
    # The model occasionally places one tag in two concepts. Assign each member
    # to exactly one concept deterministically: bigger concept wins (more members,
    # then more cards), so card_count is never double-counted.
    parsed = []
    for c in concepts:
        canonical = str(c.get("canonical", "")).strip().lower()
        members = [str(m).strip().lower() for m in (c.get("members") or [])]
        members = sorted({m for m in members if m})
        if not canonical or not members:
            continue
        parsed.append((canonical, members))
    parsed.sort(key=lambda cm: (len(cm[1]), sum(counts.get(m, 0) for m in cm[1])), reverse=True)
    for canonical, members in parsed:
        members = [m for m in members if m not in covered]
        if not members:
            continue
        card_count = sum(counts.get(m, 0) for m in members)
        out_concepts.append(
            {"canonical": canonical, "members": sorted(members), "card_count": card_count}
        )
        for m in members:
            raw_to_canonical[m] = canonical
            covered.add(m)
    # safety: any tag the model dropped maps to itself, so nothing is lost
    dropped = [t for t in counts if t not in covered]
    for t in dropped:
        raw_to_canonical[t] = t
        out_concepts.append({"canonical": t, "members": [t], "card_count": counts[t]})
    out_concepts.sort(key=lambda x: x["card_count"], reverse=True)
    return {"concepts": out_concepts, "dropped_by_model": sorted(dropped)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--library-dir", default=str(ROOT / "library"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--out", default=str(ROOT / "reports" / "connection" / "vocabulary.json"))
    ap.add_argument("--facet", default=None, help="Only build one facet (topic/method/object) for a quick check.")
    args = ap.parse_args()

    library_dir = Path(args.library_dir)
    counts, n_cards = collect_tags(library_dir)
    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)

    facets = [args.facet] if args.facet else list(FACET_KEYS)
    result = {"card_count": n_cards, "model": config.model, "facets": {}, "raw_to_canonical": {}}
    for facet in facets:
        c = counts[facet]
        print(f"[{facet}] {len(c)} raw tags, {sum(c.values())} uses -> calling AI ...", flush=True)
        facet_out = normalize_facet(client, facet, c)
        result["facets"][facet] = facet_out
        result["raw_to_canonical"][facet] = {
            m: con["canonical"] for con in facet_out["concepts"] for m in con["members"]
        }
        kept = len(facet_out["concepts"])
        print(f"[{facet}] {len(c)} raw -> {kept} canonical concepts "
              f"(dropped-and-recovered: {len(facet_out['dropped_by_model'])})", flush=True)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
