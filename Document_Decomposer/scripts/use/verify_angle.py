"""Step 3 of interrogation: verify a claimed relation by an ADVERSARIAL panel of pro models.

Why this exists: the old version used a dumb keyword script to pull "relevant" sentences,
then asked ONE model to judge. It failed twice on the weakest link -- retrieval. It missed
S121's decisive sentence ("selectivity ... increases with the reduction of nanopores") because
that sentence said "nanopores"/"reduction", not the search terms "pore size"/"smaller", and
the sentence cap evicted it. So a real contradiction was wrongly called FALSE.

New design (cost is not a concern; verification runs on a handful of angles):
  0. Plain script loads the FULL text of each paper (skip refs/ack/front matter only).
     No keyword filtering -- whole sections are fed, so nothing decisive can be filtered out.
     If the papers are too large, degrade by dropping whole low-value sections (methods/intro),
     never by keyword.
  1. PROSECUTOR (pro): build the strongest case the relation is REAL; quote verbatim.
  2. DEFENSE   (pro): build the strongest case it is FALSE or merely CONDITIONAL; name the
     reconciling variable; quote verbatim. (1 and 2 are blind to each other.)
  3. Plain script verifies every quote actually exists in the source (whitespace-insensitive,
     so OCR ligature spacing like "satis fi ed" still matches). Fabricated quotes are dropped.
  4. JUDGE (pro): decides real|false|conditional from the VERIFIED quotes only, with confidence.
  5. If confidence is not high, escalate to the human (you + Claude) -- I10: never trust one
     AI verdict blindly; a human adjudicates.

Output: reports/connection/verify_<papers>.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config

CONN = ROOT / "reports" / "connection"
SKIP_SECTIONS = {"references", "acknowledgements", "front_matter", "keywords"}
HIGH_VALUE = {"abstract", "results", "results_discussion", "discussion", "conclusion"}
# Above this combined size, drop low-value sections (keep WHOLE high-value ones) rather than
# keyword-filter. ~160k chars ~ 40k tokens, well under the model context window.
MAX_CHARS = 160_000
# Default is pure pro. We tested a flash-first hybrid (cheap flash judges, escalate to pro on low
# confidence) but multi-run evidence killed it: on a subtle CONDITIONAL pair (S121-S43) pure flash
# gave three different verdicts across three runs (false/conditional/real) and labelled all of them
# HIGH confidence -- i.e. it was confidently WRONG, so the low-confidence escalation never fired and
# a wrong verdict would ship. Pure pro was stable and correct (conditional x3, high x3) on the same
# pair. Cost is not a concern for the handful of angles verified. (Hybrid still reachable via flags:
# --model deepseek-v4-flash --escalate-model deepseek-v4-pro.)
FIRST_MODEL = "deepseek-v4-pro"
ESCALATE_MODEL = "none"


def load_full_text(pid: str, hv_only: bool = False) -> str:
    path = ROOT / "library" / pid / "reading_blocks.json"
    try:
        blocks = json.loads(path.read_text(encoding="utf-8")).get("reading_blocks", [])
    except (OSError, json.JSONDecodeError):
        return ""
    parts = []
    for b in sorted(blocks, key=lambda x: x.get("order", 0)):
        sec = b.get("section_kind", "")
        if sec in SKIP_SECTIONS:
            continue
        if hv_only and sec not in HIGH_VALUE:
            continue
        t = (b.get("text") or "").strip()
        cap = (b.get("caption") or "").strip()
        if t:
            parts.append(f"«{sec}» {t}")
        if cap:
            parts.append(f"«{sec}/caption» {cap}")
    return "\n".join(parts)


def assemble(pids: list[str]) -> tuple[dict[str, str], str]:
    texts = {pid: load_full_text(pid) for pid in pids}
    if sum(len(t) for t in texts.values()) > MAX_CHARS:
        texts = {pid: load_full_text(pid, hv_only=True) for pid in pids}
        return texts, "high-value sections only (full text exceeded budget)"
    return texts, "full text"


def norm(s: str) -> str:
    """Whitespace-insensitive, lowercase -- so 'satis fi ed' (OCR ligature) matches 'satisfied'."""
    return re.sub(r"\s+", "", s or "").lower()


def check_quotes(evidence: list[dict], source_norm: dict[str, str]) -> list[dict]:
    """A quote is verified if it exists in its paper's source. Quotes often contain an ellipsis
    ('...' / '…') joining two non-adjacent fragments; split on it and require EVERY fragment to
    appear, so a legitimate elided quote is not falsely rejected (the bug that flipped the S08-S28
    vug verdict to 'real')."""
    out = []
    for e in evidence or []:
        pid = e.get("paper", "")
        src = source_norm.get(pid, "")
        frags = [f for f in re.split(r"\.{3,}|…", e.get("quote", "")) if len(norm(f)) >= 12]
        if frags:
            verified = bool(src) and all(norm(f) in src for f in frags)
        else:
            nq = norm(e.get("quote", ""))
            verified = len(nq) >= 12 and nq in src
        out.append({**e, "verified": bool(verified)})
    return out


PROSECUTOR = (
    "You are the PROSECUTOR, arguing the claimed relation is REAL. Read each paper's FULL text and "
    "find the sentence in EACH paper stating its finding on the exact point. Copy them VERBATIM "
    "(including OCR artifacts; do not paraphrase). For EACH piece of evidence, give your REASONING: "
    "what QUANTITY/METRIC that paper measures, under what CONDITIONS, and why this establishes a "
    "genuine opposition on the SAME quantity under comparable conditions. Then give an overall "
    "reasoned argument for why it is a real contradiction. If the case for REAL is genuinely weak, "
    "say so honestly. COVERAGE: supply at least one verbatim quote for EVERY paper in the material; "
    "search the whole paper (abstract, results, discussion, conclusion, figure captions) until you "
    "find each paper's statement on the point. If a paper truly has no relevant sentence after a "
    "thorough search, say so explicitly -- do not silently omit it. NEVER invent a quote."
)
DEFENSE = (
    "You are the DEFENSE, arguing the relation is NOT a real contradiction. Using verbatim source "
    "+ explicit REASONING, show why the claim is FALSE, CONDITIONAL, or OVERSTATED/INCOMPLETE. "
    "Check, in order: (1) Do the two papers measure the SAME quantity? Flagged contradictions are "
    "often FALSE because they compare DIFFERENT quantities (e.g. flux vs permeability, sweep vs "
    "displacement efficiency, adsorption amount vs selectivity, one gas's amount vs another's) -- "
    "if so, quote each paper's measured quantity and reason why they are not comparable. (Different "
    "quantity means the PROPERTY ITSELF differs, e.g. flux vs permeability -- NOT the same property "
    "measured in a different system; that is conditional, not false.) (2) Do they "
    "operate under different CONDITIONS (substrate/mineral, pore size/structure, pressure, "
    "temperature, phase, wettability, method/force field)? -- if so, name the reconciling variable. "
    "(3) Is one paper's claim merely OVERSTATED beyond what its quote supports? Quote VERBATIM for "
    "every point and reason explicitly. COVERAGE: try to supply a verbatim quote for EVERY paper "
    "(search abstract/results/discussion/conclusion/captions); if a paper has no relevant sentence "
    "after thorough search, say so explicitly. NEVER invent a quote."
)
JUDGE = (
    "You are the JUDGE. Do NOT merely tally votes or pick a side -- reason INDEPENDENTLY from the "
    "VERIFIED quotes only (quotes marked UNVERIFIED do not exist in the source; give them ZERO "
    "weight). Decide by this ORDERED procedure:\n"
    "1. Name each paper's MEASURED QUANTITY -- the physical property itself (e.g. 'permeability', "
    "'molecular flux', 'displacement efficiency', 'CO2 selectivity'), INDEPENDENT of the system it "
    "is measured in.\n"
    "2. If the papers report DIFFERENT properties (e.g. flux vs permeability; sweep vs displacement "
    "efficiency; CH4 amount vs CO2 amount) -> 'false' (not comparable).\n"
    "3. If they report the SAME property, compare SYSTEM/CONDITIONS (substrate, pore size/structure, "
    "pressure, temperature, phase, network vs single pore...):\n"
    "   - same property + comparable conditions + opposite results -> 'real';\n"
    "   - same property + different system/conditions -> 'conditional' (name that as the reconciling "
    "variable). Measuring the SAME property in a different system/structure/material is NOT a "
    "different quantity -- it is 'conditional', NEVER 'false'.\n"
    "4. If a paper central to the claim has NO verified quote about its finding -> 'undetermined' "
    "(name the missing paper). 'false' requires POSITIVE evidence; never infer it from absence.\n"
    "WORKED EXAMPLES: permeability in a 3D pore network vs in a single nanotube = SAME quantity "
    "(permeability), different system -> conditional (reconciling = pore structure). Flux "
    "(amount/time) vs permeability (flux per pressure gradient) = DIFFERENT quantities -> false.\n"
    "In the explanation, write each paper's measured quantity and your reasoning. Set confidence "
    "'high'|'medium'|'low' (low when verified evidence is thin). Be honest; do NOT split the "
    "difference just to be safe."
)

ADV_SCHEMA = (
    'Respond with JSON: {"position":"real|false|conditional","reconciling_variable":"<or null>",'
    '"evidence":[{"paper":"Sxx","quote":"<verbatim sentence>",'
    '"why":"<your reasoning: what quantity/condition this is, and why it does/does not support a real contradiction>"}],'
    '"argument":"<your overall reasoning, 2-4 sentences>"}'
)
JUDGE_SCHEMA = (
    'Respond with JSON: {"verdict":"real|false|conditional|undetermined","reconciling_variable":"<or null>",'
    '"confidence":"high|medium|low","decisive_quotes":[{"paper":"Sxx","quote":"<verbatim>"}],'
    '"explanation":"<2-4 sentences>"}'
)


def run_advocate(client, role_system: str, claim: str, texts: dict[str, str]) -> dict:
    blocks = "\n\n".join(f"===== {pid} (FULL TEXT) =====\n{txt or '(no text found)'}"
                         for pid, txt in texts.items())
    user = f"CLAIMED relation to argue about: {claim}\n\nThe papers:\n\n{blocks}"
    return client.chat_json([{"role": "system", "content": role_system},
                             {"role": "user", "content": user}], ADV_SCHEMA)


def fmt_case(name: str, brief: dict, checked: list[dict]) -> str:
    lines = [f"{name} POSITION: {brief.get('position', '')}",
             f"{name} reconciling_variable: {brief.get('reconciling_variable')}",
             f"{name} ARGUMENT: {brief.get('argument', '')}",
             f"{name} EVIDENCE:"]
    for e in checked:
        tag = "VERIFIED" if e["verified"] else "UNVERIFIED(ignore)"
        lines.append(f"  - [{tag}] {e.get('paper')}: \"{e.get('quote', '')}\"  ({e.get('why', '')})")
    return "\n".join(lines)


def run_panel(model: str, claim: str, texts: dict[str, str], source_norm: dict[str, str],
              config_path: Path | None) -> dict:
    config = replace(load_ai_config(ROOT, config_path), model=model)
    client = OpenAICompatibleClient(config)
    print(f"[{model}] PROSECUTOR (argues REAL) ...")
    pros = run_advocate(client, PROSECUTOR, claim, texts)
    print(f"[{model}] DEFENSE (argues FALSE/CONDITIONAL) ...")
    defe = run_advocate(client, DEFENSE, claim, texts)
    pros_checked = check_quotes(pros.get("evidence", []), source_norm)
    defe_checked = check_quotes(defe.get("evidence", []), source_norm)
    print(f"[{model}] JUDGE (verified quotes only) ...")
    judge_user = (f"CLAIM: {claim}\n\n"
                  + fmt_case("PROSECUTOR", pros, pros_checked) + "\n\n"
                  + fmt_case("DEFENSE", defe, defe_checked))
    verdict = client.chat_json([{"role": "system", "content": JUDGE},
                                {"role": "user", "content": judge_user}], JUDGE_SCHEMA)
    return {
        "model": model,
        "prosecutor": {**pros, "evidence_checked": pros_checked},
        "defense": {**defe, "evidence_checked": defe_checked},
        "judge": verdict,
    }


def print_panel(panel: dict) -> None:
    v = panel["judge"]
    print("\n" + "=" * 60)
    print(f"[{panel['model']}] VERDICT: {v.get('verdict')}   confidence: {v.get('confidence')}"
          f"   reconciling_variable: {v.get('reconciling_variable')}")
    for q in v.get("decisive_quotes", []):
        print(f"  [{q.get('paper')}] \"{q.get('quote', '')[:150]}\"")
    print(f"explanation: {v.get('explanation', '')}")
    pc, dc = panel["prosecutor"]["evidence_checked"], panel["defense"]["evidence_checked"]
    print(f"quote check: prosecutor {sum(e['verified'] for e in pc)}/{len(pc)} verified, "
          f"defense {sum(e['verified'] for e in dc)}/{len(dc)} verified")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--papers", required=True, help="Comma list, e.g. S121,S43")
    ap.add_argument("--claim", required=True, help="The claimed relation/thesis to test.")
    ap.add_argument("--model", default=FIRST_MODEL, help=f"First-pass model (default {FIRST_MODEL}).")
    ap.add_argument("--escalate-model", default=ESCALATE_MODEL,
                    help=f"Re-run with this if first pass is not confident (default {ESCALATE_MODEL}; "
                         "'none' to disable).")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    pids = [p.strip() for p in args.papers.split(",") if p.strip()]
    texts, note = assemble(pids)
    source_norm = {pid: norm(t) for pid, t in texts.items()}
    cfg = Path(args.config) if args.config else None
    print(f"loaded {note}: " + ", ".join(f"{pid}={len(texts[pid])}c" for pid in pids))

    first = run_panel(args.model, args.claim, texts, source_norm, cfg)
    print_panel(first)

    final = first
    escalated = False
    esc_model = args.escalate_model
    if first["judge"].get("confidence") != "high" and esc_model and esc_model.lower() != "none" \
            and esc_model != args.model:
        print(f"\n⚠ {args.model} not confident -> escalating to {esc_model} ...")
        final = run_panel(esc_model, args.claim, texts, source_norm, cfg)
        print_panel(final)
        escalated = True

    still_unsure = final["judge"].get("confidence") != "high"
    result = {
        "papers": pids, "claim": args.claim, "source": note,
        "first_pass": first,
        "escalated": escalated,
        "final": final,
        "escalate_to_human": still_unsure,
    }
    out = CONN / f"verify_{'_'.join(pids)}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "#" * 60)
    fv = final["judge"]
    tag = f"{first['model']}->{final['model']}" if escalated else final["model"]
    print(f"FINAL [{tag}]: {fv.get('verdict')}  confidence={fv.get('confidence')}  "
          f"reconciling={fv.get('reconciling_variable')}")
    if still_unsure:
        print("⚠ still not high confidence -> ESCALATE: a human (you + Claude) should adjudicate.")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
