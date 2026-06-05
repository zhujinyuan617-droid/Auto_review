from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from docdecomp.evidence_synthesis import load_json, normalize_space
from docdecomp.io_utils import atomic_write_csv_dicts, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare article syntheses against a manual baseline and across rounds.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--baseline", default=str(ROOT / "reports" / "manual_article_synthesis_baseline.json"))
    parser.add_argument("--paper-id", action="append", help="Paper id. May be repeated.")
    parser.add_argument("--syntheses-name", action="append", required=True, help="Syntheses filename to audit. May be repeated.")
    parser.add_argument("--report", default=str(ROOT / "reports" / "synthesis_stability_audit.csv"))
    parser.add_argument("--summary", default=str(ROOT / "reports" / "synthesis_stability_summary.json"))
    return parser.parse_args()


def text_blob(synthesis: dict[str, Any]) -> str:
    values = [
        synthesis.get("claim"),
        synthesis.get("reasoning"),
        synthesis.get("scope"),
        " ".join(str(value) for value in synthesis.get("limitations") or []),
    ]
    return normalize_space(" ".join(str(value or "") for value in values)).lower()


def term_group_hit(blob: str, group: list[str]) -> bool:
    return any(normalize_space(term).lower() in blob for term in group)


def theme_match_score(theme: dict[str, Any], synthesis: dict[str, Any]) -> dict[str, Any]:
    expected_ids = set(str(value) for value in theme.get("expected_atom_ids") or [])
    support_ids = set(str(value) for value in synthesis.get("supporting_evidence_atom_ids") or [])
    overlap = sorted(expected_ids & support_ids)
    blob = text_blob(synthesis)
    term_hits = [
        index
        for index, group in enumerate(theme.get("term_groups") or [])
        if term_group_hit(blob, group)
    ]
    support_ok = len(overlap) >= int(theme.get("min_support_overlap") or 1)
    terms_ok = len(term_hits) >= int(theme.get("min_term_group_hits") or 1)
    return {
        "support_overlap": len(overlap),
        "support_overlap_ids": overlap,
        "term_group_hits": len(term_hits),
        "term_group_hit_indexes": term_hits,
        "covered": support_ok or terms_ok,
    }


def best_theme_match(theme: dict[str, Any], syntheses: list[dict[str, Any]]) -> dict[str, Any]:
    best: dict[str, Any] = {
        "synthesis_id": "",
        "support_overlap": 0,
        "support_overlap_ids": [],
        "term_group_hits": 0,
        "term_group_hit_indexes": [],
        "covered": False,
    }
    for synthesis in syntheses:
        score = theme_match_score(theme, synthesis)
        if (
            score["covered"] and not best["covered"]
            or score["support_overlap"] > best["support_overlap"]
            or (
                score["support_overlap"] == best["support_overlap"]
                and score["term_group_hits"] > best["term_group_hits"]
            )
        ):
            best = {
                "synthesis_id": str(synthesis.get("synthesis_id") or ""),
                **score,
            }
    return best


def normalize_signature_text(text: str) -> str:
    value = normalize_space(text).lower()
    value = re.sub(r"\b\d{4}\b", "", value)
    value = re.sub(r"\b(s\d+)-syn-\d+\b", "", value)
    value = re.sub(r"\b(s\d+)-evatom-\d+\b", "", value)
    return normalize_space(value)


def synthesis_signature(synthesis: dict[str, Any]) -> str:
    support = sorted(str(value) for value in synthesis.get("supporting_evidence_atom_ids") or [])
    claim_terms = normalize_signature_text(str(synthesis.get("claim") or ""))
    claim_terms = " ".join(claim_terms.split()[:18])
    return f"{synthesis.get('synthesis_type')}|{'+'.join(support)}|{claim_terms}"


def audit_one(paper_id: str, syntheses_name: str, library_dir: Path, baseline: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    package = load_json(library_dir / paper_id / syntheses_name)
    syntheses = [item for item in package.get("paper_syntheses") or [] if isinstance(item, dict)]
    themes = baseline["papers"][paper_id]["themes"]
    rows: list[dict[str, Any]] = []
    covered_count = 0
    for theme in themes:
        best = best_theme_match(theme, syntheses)
        if best["covered"]:
            covered_count += 1
        rows.append(
            {
                "paper_id": paper_id,
                "syntheses_name": syntheses_name,
                "theme_id": theme["theme_id"],
                "covered": "yes" if best["covered"] else "no",
                "best_synthesis_id": best["synthesis_id"],
                "support_overlap": best["support_overlap"],
                "support_overlap_ids": " ".join(best["support_overlap_ids"]),
                "term_group_hits": best["term_group_hits"],
            }
        )
    signatures = sorted(synthesis_signature(synthesis) for synthesis in syntheses)
    summary = {
        "paper_id": paper_id,
        "syntheses_name": syntheses_name,
        "synthesis_count": len(syntheses),
        "theme_count": len(themes),
        "covered_count": covered_count,
        "coverage": round(covered_count / max(1, len(themes)), 4),
        "signatures": signatures,
    }
    return rows, summary


def jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    return round(len(left_set & right_set) / max(1, len(left_set | right_set)), 4)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    baseline = load_json(Path(args.baseline))
    library_dir = Path(args.library_dir)
    paper_ids = args.paper_id or sorted(baseline.get("papers", {}).keys())

    rows: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for paper_id in paper_ids:
        for syntheses_name in args.syntheses_name:
            one_rows, summary = audit_one(paper_id, syntheses_name, library_dir, baseline)
            rows.extend(one_rows)
            summaries.append(summary)

    stability: list[dict[str, Any]] = []
    for paper_id in paper_ids:
        paper_summaries = [item for item in summaries if item["paper_id"] == paper_id]
        for left, right in zip(paper_summaries, paper_summaries[1:]):
            stability.append(
                {
                    "paper_id": paper_id,
                    "left": left["syntheses_name"],
                    "right": right["syntheses_name"],
                    "signature_jaccard": jaccard(left["signatures"], right["signatures"]),
                    "coverage_left": left["coverage"],
                    "coverage_right": right["coverage"],
                }
            )

    theme_stability: list[dict[str, Any]] = []
    for paper_id in paper_ids:
        themes = baseline["papers"][paper_id]["themes"]
        for theme in themes:
            theme_rows = [
                row for row in rows
                if row["paper_id"] == paper_id and row["theme_id"] == theme["theme_id"]
            ]
            covered_rounds = sum(1 for row in theme_rows if row["covered"] == "yes")
            best_support_sets = sorted(
                set(row["support_overlap_ids"] for row in theme_rows if row["covered"] == "yes")
            )
            theme_stability.append(
                {
                    "paper_id": paper_id,
                    "theme_id": theme["theme_id"],
                    "round_count": len(theme_rows),
                    "covered_rounds": covered_rounds,
                    "stable_coverage": covered_rounds == len(theme_rows),
                    "support_signature_count": len(best_support_sets),
                }
            )

    report_path = Path(args.report)
    atomic_write_csv_dicts(
        report_path,
        [
            "paper_id",
            "syntheses_name",
            "theme_id",
            "covered",
            "best_synthesis_id",
            "support_overlap",
            "support_overlap_ids",
            "term_group_hits",
        ],
        rows,
    )
    summary_path = Path(args.summary)
    write_json(summary_path, {"summaries": summaries, "stability": stability, "theme_stability": theme_stability})
    print(f"Wrote {report_path}")
    print(f"Wrote {summary_path}")
    for summary in summaries:
        print(
            f"{summary['paper_id']} {summary['syntheses_name']}: "
            f"coverage={summary['covered_count']}/{summary['theme_count']} "
            f"syntheses={summary['synthesis_count']}"
        )
    for item in stability:
        print(
            f"{item['paper_id']} {item['left']} -> {item['right']}: "
            f"signature_jaccard={item['signature_jaccard']}"
        )
    unstable_themes = [item for item in theme_stability if not item["stable_coverage"]]
    if unstable_themes:
        print("Unstable theme coverage:")
        for item in unstable_themes:
            print(f"{item['paper_id']} {item['theme_id']}: {item['covered_rounds']}/{item['round_count']}")
    failed = [summary for summary in summaries if summary["coverage"] < 1.0]
    return 1 if failed or unstable_themes else 0


if __name__ == "__main__":
    raise SystemExit(main())
