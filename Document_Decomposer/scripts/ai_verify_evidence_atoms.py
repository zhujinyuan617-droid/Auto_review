from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.ai_client import OpenAICompatibleClient, load_ai_config, run_ai_cli
from docdecomp.evidence_synthesis import load_json, write_json


# Independent claim-grounding VERIFIER (the "checker" role), deliberately kept
# separate from the atom GENERATOR (ai_build_evidence_atoms.py). Boundaries:
#   - IN scope:  judge whether each atom's minimal_claim is fully and only
#                supported by its own quote.
#   - OUT scope: it does NOT generate atoms, pick quotes, edit JSON, check that
#                the quote is verbatim-in-block (the mechanical validator's job),
#                or look at metadata/card/syntheses.
# Audit-only by default: writes evidence_atoms.verify.json, mutates nothing.

SYSTEM = (
    "You are an independent claim-grounding verifier for one paper's evidence atoms. "
    "You did NOT write these atoms and you must not rewrite, regenerate, or re-pick evidence. "
    "Your ONLY job: for each atom, decide whether its minimal_claim is fully AND only supported by its own quote. "
    "Be strict and literal. Return strict JSON only."
)


def build_messages(paper_id: str, atoms: list[dict]) -> list[dict[str, str]]:
    items = [
        {
            "evidence_atom_id": a.get("evidence_atom_id"),
            "atom_type": a.get("atom_type"),
            "minimal_claim": a.get("minimal_claim"),
            "quote": a.get("quote"),
        }
        for a in atoms
    ]
    user = (
        "For EVERY atom below, output a verdict.\n"
        "verdict = 'SUPPORTED' only if the quote literally supports the ENTIRE minimal_claim. "
        "verdict = 'DRIFT' if the claim adds ANY fact not present in the quote (a number, unit, condition such as "
        "temperature/pressure/pore size, comparison, or attribution), or contradicts the quote, or generalizes beyond it. "
        "A light paraphrase of the quote is fine and stays SUPPORTED. Judge ONLY claim-vs-quote; do not judge whether the "
        "quote itself is real or complete.\n"
        "Return ONE JSON object: {\"paper_id\": \"" + paper_id + "\", \"verifications\": [ {\"evidence_atom_id\": str, "
        "\"verdict\": \"SUPPORTED\"|\"DRIFT\", \"drift_type\": \"none\"|\"added_number\"|\"added_condition\"|"
        "\"added_comparison\"|\"attribution\"|\"contradiction\"|\"overreach\", \"reason\": str } ] }. "
        "Include one entry for every atom id. For SUPPORTED use drift_type 'none' and reason ''. Do not wrap in Markdown.\n"
        "Atoms JSON:\n" + json.dumps({"paper_id": paper_id, "atoms": items}, ensure_ascii=False)
    )
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Independent AI verifier: check each evidence atom's minimal_claim is fully supported by its quote."
    )
    parser.add_argument("--paper-id", default="S01")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--config", default=None, help="Path to ai.local.json. Defaults to config/ai.local.json.")
    parser.add_argument("--atoms-name", default="evidence_atoms.json")
    parser.add_argument("--output-name", default="evidence_atoms.verify.json")
    parser.add_argument("--dry-run", action="store_true", help="Write prompt preview instead of calling AI.")
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    paper_dir = Path(args.library_dir) / args.paper_id
    package = load_json(paper_dir / args.atoms_name)
    atoms = package.get("evidence_atoms") or []
    messages = build_messages(args.paper_id, atoms)

    if args.dry_run:
        write_json(paper_dir / "evidence_atoms.verify.prompt.json", {"messages": messages})
        print(f"Prompt preview: {paper_dir / 'evidence_atoms.verify.prompt.json'}")
        return 0

    config = load_ai_config(ROOT, Path(args.config) if args.config else None)
    client = OpenAICompatibleClient(config)
    schema_hint = (
        "Return one JSON object with keys paper_id and verifications. verifications is an array; each item has "
        "evidence_atom_id, verdict ('SUPPORTED' or 'DRIFT'), drift_type, reason. Do not wrap in Markdown."
    )
    result = client.chat_json(messages, schema_hint)

    verifs = result.get("verifications") or []
    seen = {v.get("evidence_atom_id") for v in verifs}
    atom_ids = [a.get("evidence_atom_id") for a in atoms]
    unjudged = [aid for aid in atom_ids if aid not in seen]
    drift = [v for v in verifs if v.get("verdict") == "DRIFT"]
    report = {
        "paper_id": args.paper_id,
        "atom_count": len(atoms),
        "verified_count": len(verifs),
        "drift_count": len(drift),
        "unjudged_atom_ids": unjudged,
        "verifications": verifs,
    }
    write_json(paper_dir / args.output_name, report)
    flag = " (UNJUDGED: " + ",".join(unjudged) + ")" if unjudged else ""
    print(f"{args.paper_id}: atoms={len(atoms)} verified={len(verifs)} DRIFT={len(drift)}{flag}")
    for v in drift:
        print(f"  DRIFT {v.get('evidence_atom_id')} [{v.get('drift_type')}]: {str(v.get('reason'))[:140]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_ai_cli(main))
