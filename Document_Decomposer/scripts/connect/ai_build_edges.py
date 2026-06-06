"""Step (2b) of the link network: AI judges the relation TYPE of each candidate edge.

Reads reports/connection/candidate_edges.json. Each undirected edge is assigned to
one focal paper (the lexicographically smaller id) so it is judged exactly once.
For each focal paper, ONE AI call is made that shows the focal card's coarse summary
plus each candidate neighbour's coarse summary and the concepts they share, and asks
the model to label every edge:

  supports | contradicts | extends | fills_gap | shared_context (-> dropped)

Coarse / direction-level only: the model must cite the shared canonical concept in
its rationale, must NOT treat "same topic" as supports, must NOT use precise numbers,
and must fall back to shared_context when unsure (drop the edge rather than invent a
relation). Precise facts stay in the atoms layer for later drill-down.

Calls run concurrently (DeepSeek tolerates it) and are cached per focal paper so
reruns / resumes are cheap. Output: reports/connection/edges.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config

CONN = ROOT / "reports" / "connection"
PROMPT_VERSION = "edges-v4"  # v4: judge from slim card summary (distil-once); source optional

VALID = {"supports", "contradicts", "complements", "shared_context"}
DIRECTIONAL = {"complements"}  # optional builds-on direction

SYSTEM = (
    "You label the relationship between a focal research paper and each of several "
    "candidate neighbour papers, using only coarse, direction-level judgements "
    "(never precise numbers). Allowed labels:\n"
    "- supports: same-direction agreement on a SPECIFIC finding or mechanism (not mere shared topic); "
    "their conclusions reinforce each other.\n"
    "- contradicts: tension; on the same question their conclusions or applicability conflict.\n"
    "- complements: the two study the SAME specific system / problem but cover DIFFERENT pieces "
    "(different variable, material, method, or angle) -- they neither simply agree nor disagree, but "
    "together they fit as combinable parts of one picture. If one paper clearly builds on / generalizes "
    "the other, STILL use complements and give the BASE paper id (the one being built upon).\n"
    "- shared_context: only a coincidental or single generic overlap, or genuinely different problems.\n\n"
    "HARD RULES:\n"
    "0. Judge from each paper's `summary` (direction-level findings distilled from the paper). "
    "If `abstract`/`conclusion` are also provided, use them to resolve doubt.\n"
    "1. Your rationale MUST reference the concrete concept(s) the two papers share.\n"
    "2. Do NOT treat 'both about the same topic' as supports. Agreement must be about a "
    "specific finding or mechanism, not mere topical overlap.\n"
    "3. Do NOT assert precise numbers. Judge direction only.\n"
    "4. STRENGTH-AWARE DEFAULT: if the two papers share a SPECIFIC cluster of concepts "
    "(a system / material / method, not just one generic word) but you find no explicit agreement or "
    "disagreement, label complements -- do NOT drop it. Use shared_context ONLY when the overlap is a "
    "single generic / coincidental concept, or the papers truly address different problems."
)

SCHEMA_HINT = (
    'Respond with a single JSON object: '
    '{"edges":[{"neighbor":"<id>","relation":"supports|contradicts|complements|shared_context",'
    '"base":"<id or null>","rationale":"<one sentence citing the shared concept>"}]}. '
    "Include every neighbour exactly once. base is required only when relation is complements AND one "
    "paper clearly builds on the other (else null)."
)


# architecture v2 / option (甲): relation typing reads the slim card's coarse SUMMARY
# (distilled once from focused reading, then trusted -- "distil once, reuse"). The paper's
# abstract+conclusion are fed ONLY when --source on (e.g. to spot-check edge quality).
INCLUDE_SOURCE = False  # set from CLI (--source on)
ABSTRACT_KINDS = {"abstract"}
CONCLUSION_KINDS = {"conclusion"}
FALLBACK_KINDS = {"discussion", "results_discussion"}  # used only if abstract+conclusion empty


def _blocks_text(blocks, kinds, max_chars):
    parts = [b.get("text", "") or "" for b in blocks if b.get("section_kind") in kinds]
    return " ".join(parts).strip()[:max_chars]


def load_paper_context(pid: str) -> dict:
    lib = ROOT / "library" / pid
    try:
        blocks = json.loads((lib / "reading_blocks.json").read_text(encoding="utf-8")).get("reading_blocks", [])
    except (OSError, json.JSONDecodeError):
        blocks = []
    try:
        card = json.loads((lib / "literature_card.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        card = {}

    abstract = _blocks_text(blocks, ABSTRACT_KINDS, 1200)
    conclusion = _blocks_text(blocks, CONCLUSION_KINDS, 1200)
    if not (abstract or conclusion):  # papers Docling didn't label -> fall back to discussion
        abstract = _blocks_text(blocks, FALLBACK_KINDS, 1500)

    # coarse summary: slim card (v2) has card["summary"]; thick card -> derive from key_findings
    summ = card.get("summary")
    if isinstance(summ, dict):
        obj = summ.get("objective", "")
        parts = ([obj] if obj else []) + list(summ.get("main_findings") or [])
        summary_text = " | ".join(parts)
    else:
        cq = (card.get("core_question") or {}).get("claim", "")
        kfs = [kf.get("claim", "") for kf in (card.get("key_findings") or [])[:5] if kf.get("claim")]
        summary_text = " | ".join(([cq] if cq else []) + kfs)

    return {
        "id": pid,
        "title": (card.get("paper", {}) or {}).get("title", ""),
        "abstract": abstract,
        "conclusion": conclusion,
        "summary": summary_text,
    }


def build_messages(focal: dict, neighbours: list[dict]) -> list[dict]:
    def fmt(card):
        parts = [f"id: {card['id']}", f"title: {card['title']}"]
        if card.get("summary"):
            parts.append(f"summary (direction-level findings): {card['summary']}")
        if INCLUDE_SOURCE:
            if card.get("abstract"):
                parts.append(f"abstract: {card['abstract']}")
            if card.get("conclusion"):
                parts.append(f"conclusion: {card['conclusion']}")
        return "\n".join(parts)

    blocks = []
    for nb in neighbours:
        shared = "; ".join(f"{f}:{'/'.join(v)}" for f, v in nb["shared"].items())
        strength = "strong" if nb.get("score", 0) >= 6 else "medium"
        n_shared = sum(len(v) for v in nb["shared"].values())
        blocks.append(
            f"--- neighbour {nb['card']['id']} "
            f"(shared concepts [{strength}, {n_shared} concepts] -> {shared}) ---\n{fmt(nb['card'])}"
        )
    user = (
        "FOCAL PAPER:\n" + fmt(focal) + "\n\n"
        f"CANDIDATE NEIGHBOURS ({len(neighbours)}). For each, label its relation to the focal paper.\n\n"
        + "\n\n".join(blocks)
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def cache_key(focal_id, neighbours, model):
    h = hashlib.sha256()
    h.update(PROMPT_VERSION.encode())
    h.update(str(INCLUDE_SOURCE).encode())
    h.update(model.encode())
    h.update(focal_id.encode())
    for nb in sorted(neighbours, key=lambda x: x["card"]["id"]):
        h.update(nb["card"]["id"].encode())
        h.update(json.dumps(nb["shared"], sort_keys=True).encode())
    return h.hexdigest()[:16]


def judge_focal(client, focal_id, neighbours, model, cache_dir, force):
    ck = cache_key(focal_id, neighbours, model)
    cpath = cache_dir / f"{focal_id}_{ck}.json"
    if cpath.exists() and not force:
        return json.loads(cpath.read_text(encoding="utf-8")), True
    focal = load_paper_context(focal_id)
    resp = client.chat_json(build_messages(focal, neighbours), SCHEMA_HINT)
    result = resp.get("edges", []) if isinstance(resp, dict) else []
    cpath.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result, False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--candidates", default=str(CONN / "candidate_edges.json"))
    ap.add_argument("--out", default=str(CONN / "edges.json"))
    ap.add_argument("--config", default=None)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--source", choices=["off", "on"], default="off",
                    help="Also feed abstract+conclusion to relation judging (default off: summary only).")
    ap.add_argument("--force", action="store_true", help="Ignore cache and re-call the model.")
    args = ap.parse_args()

    global INCLUDE_SOURCE
    INCLUDE_SOURCE = (args.source == "on")

    cand = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    # group edges by focal = min(a,b)
    groups: dict[str, list] = defaultdict(list)
    edge_meta = {}
    for e in cand["edges"]:
        a, b = sorted((e["a"], e["b"]))
        groups[a].append({"card": load_paper_context(b), "shared": e["shared"], "score": e["candidate_score"]})
        edge_meta[(a, b)] = {"shared": e["shared"], "candidate_score": e["candidate_score"]}

    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)
    cache_dir = CONN / "edge_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    focals = sorted(groups)
    print(f"{len(edge_meta)} candidate edges across {len(focals)} focal papers; workers={args.workers}", flush=True)

    results = {}
    lock = threading.Lock()
    done = [0]

    def work(focal_id):
        out, cached = judge_focal(client, focal_id, groups[focal_id], config.model, cache_dir, args.force)
        with lock:
            done[0] += 1
            tag = "cache" if cached else "ai"
            print(f"  [{done[0]}/{len(focals)}] {focal_id} ({len(groups[focal_id])} nbrs) [{tag}]", flush=True)
        return focal_id, out

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(work, f) for f in focals]
        for fut in as_completed(futs):
            try:
                fid, out = fut.result()
                results[fid] = out
            except Exception as exc:  # one bad focal must not kill the batch
                print(f"  ! focal failed: {exc}", flush=True)

    # assemble edges.json
    edges = []
    counts = Counter()
    for focal_id, judged in results.items():
        for j in judged:
            nb = str(j.get("neighbor", "")).strip()
            rel = str(j.get("relation", "")).strip()
            a, b = sorted((focal_id, nb))
            if (a, b) not in edge_meta or rel not in VALID:
                continue
            counts[rel] += 1
            if rel == "shared_context":
                continue
            direction = None
            if rel in DIRECTIONAL:
                base = str(j.get("base", "")).strip()
                if base == a:
                    direction = "a->b"  # b builds on a
                elif base == b:
                    direction = "b->a"  # a builds on b
            meta = edge_meta[(a, b)]
            edges.append({
                "a": a, "b": b, "relation": rel, "direction": direction,
                "shared": meta["shared"], "candidate_score": meta["candidate_score"],
                "rationale": str(j.get("rationale", "")).strip(), "model": config.model,
            })
    edges.sort(key=lambda e: e["candidate_score"], reverse=True)

    out = {
        "model": config.model, "prompt_version": PROMPT_VERSION,
        "n_candidate_edges": len(edge_meta), "n_edges": len(edges),
        "relation_counts": dict(counts), "edges": edges,
    }
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nrelation counts (incl. dropped shared_context): {dict(counts)}")
    print(f"kept {len(edges)} typed edges (dropped {counts.get('shared_context',0)} shared_context)")
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
