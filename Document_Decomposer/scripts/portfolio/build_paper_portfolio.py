from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]


SCIENTIFIC_CANDIDATES = [
    {
        "key": "clay_selectivity_flagship",
        "manuscript_type": "large_review",
        "status": "already_generated_flagship",
        "title": "Clay-controlled gas adsorption selectivity in shale systems: mechanisms, boundary conditions, and evidence synthesis",
        "core_question": "How do clay mineralogy, surface charge, cation exchange, pore structure, and water jointly control CO2/CH4 adsorption selectivity in shale systems?",
        "required_any": [["clay", "montmorillonite", "illite", "kaolinite", "chlorite"]],
        "focus_terms": [
            "adsorption",
            "sorption",
            "selectivity",
            "co2",
            "ch4",
            "methane",
            "surface charge",
            "cation",
            "water",
            "pore",
            "nanopore",
            "shale",
            "mineral",
        ],
        "target_journal_direction": "energy geoscience / shale gas / adsorption review",
        "innovation_points": [
            "Reframes clay-controlled adsorption selectivity as a coupled mineralogy-charge-water-pore problem.",
            "Turns contradictions about clay versus non-clay minerals into boundary-condition questions.",
            "Connects molecular simulation and experimental evidence into a traceable synthesis.",
        ],
        "figure_strategy": "Mechanism schematic, contradiction map, evidence matrix, multi-panel source figures for clay/water/selectivity.",
    },
    {
        "key": "water_hydration_adsorption_transport",
        "manuscript_type": "large_review",
        "status": "candidate",
        "title": "Water and hydration control of gas adsorption and transport in shale nanopores",
        "core_question": "When does water suppress total uptake, when can it enhance apparent selectivity, and how does hydration couple adsorption to diffusion and displacement?",
        "required_any": [["water", "hydration", "moisture", "h2o", "swelling", "water content"]],
        "focus_terms": [
            "adsorption",
            "sorption",
            "diffusion",
            "transport",
            "selectivity",
            "co2",
            "ch4",
            "methane",
            "nanopore",
            "clay",
            "kerogen",
            "illite",
            "montmorillonite",
            "kaolinite",
            "pore",
        ],
        "target_journal_direction": "fuel / adsorption science / molecular simulation review",
        "innovation_points": [
            "Separates water's site-blocking role from its non-monotonic selectivity effects.",
            "Links hydration, swelling, cation solvation, adsorption, and diffusion in one framework.",
            "Identifies dry/wet boundary conditions that explain divergent shale gas adsorption results.",
        ],
        "figure_strategy": "Hydration mechanism panels, water-content boundary map, adsorption-diffusion evidence matrix.",
    },
    {
        "key": "boundary_condition_contradictions",
        "manuscript_type": "large_review_or_perspective",
        "status": "candidate",
        "title": "Boundary-condition framework for contradictory shale adsorption simulations",
        "core_question": "Which model choices and reservoir conditions explain contradictory conclusions about clay, quartz, kerogen, water, pore size, pressure, and temperature effects?",
        "required_any": [
            ["simulation", "molecular dynamics", "monte carlo", "gcmc", "model"],
            ["pressure", "temperature", "pore size", "water", "quartz", "kerogen", "mineral", "composite", "slit"],
        ],
        "focus_terms": [
            "contradict",
            "boundary",
            "condition",
            "pressure",
            "temperature",
            "pore size",
            "water",
            "dry",
            "hydrated",
            "quartz",
            "kerogen",
            "clay",
            "composite",
            "organic",
            "inorganic",
            "adsorption",
            "diffusion",
            "selectivity",
        ],
        "target_journal_direction": "computational geoscience / molecular simulation perspective",
        "innovation_points": [
            "Treats contradictions as the central object rather than as noise to be smoothed away.",
            "Builds a boundary-condition grammar for pore size, mineral assembly, water, pressure, temperature, and model type.",
            "Can become a high-value perspective if focused on how to design comparable simulations.",
        ],
        "figure_strategy": "Contradiction network, boundary-condition decision tree, model-comparison matrix.",
    },
    {
        "key": "multiscale_ai_modeling_adsorption_diffusion",
        "manuscript_type": "large_review",
        "status": "candidate",
        "title": "Multiscale and AI-assisted modeling of adsorption-diffusion coupling in shale systems",
        "core_question": "How can GCMC, MD, DFT, SLD/continuum models, experiments, and machine learning be connected into a predictive workflow for shale gas adsorption and transport?",
        "required_any": [["simulation", "molecular dynamics", "monte carlo", "gcmc", "dft", "sld", "machine learning", "artificial intelligence", "model"]],
        "focus_terms": [
            "adsorption",
            "diffusion",
            "transport",
            "multiscale",
            "molecular simulation",
            "molecular dynamics",
            "monte carlo",
            "gcmc",
            "dft",
            "sld",
            "machine learning",
            "artificial intelligence",
            "neural",
            "prediction",
            "workflow",
            "experiment",
        ],
        "target_journal_direction": "modeling methods / computational energy materials review",
        "innovation_points": [
            "Connects atomistic simulation, continuum modeling, experiments, and AI/ML into a workflow problem.",
            "Positions adsorption-diffusion coupling as a multiscale modeling bottleneck.",
            "Distinguishes model validation, acceleration, and interpretability tasks for AI/ML.",
        ],
        "figure_strategy": "Workflow diagram, method-by-scale map, model validation matrix, AI/ML role schematic.",
    },
    {
        "key": "co2_storage_enhanced_gas_recovery",
        "manuscript_type": "large_review",
        "status": "candidate",
        "title": "CO2 storage and enhanced gas recovery in shale and nanoporous geological media",
        "core_question": "How do adsorption selectivity, injection conditions, displacement, mineral interactions, and pore confinement govern CO2 storage and enhanced gas recovery?",
        "required_any": [["co2", "carbon dioxide", "carbon sequestration", "carbon storage", "ccus"]],
        "focus_terms": [
            "enhanced gas recovery",
            "egr",
            "sequestration",
            "storage",
            "injection",
            "displacement",
            "recovery",
            "sc-co2",
            "supercritical",
            "adsorption",
            "selectivity",
            "shale",
            "coal",
            "caprock",
            "mineralization",
        ],
        "target_journal_direction": "ccus / energy storage / reservoir engineering review",
        "innovation_points": [
            "Unifies CO2 storage and enhanced gas recovery through adsorption selectivity and displacement mechanisms.",
            "Bridges shale, coal, kerogen, and mineral nanopores under injection and reservoir conditions.",
            "Separates storage capacity, displacement efficiency, and mobility/security tradeoffs.",
        ],
        "figure_strategy": "Storage-displacement mechanism map, reservoir condition matrix, CO2 pathway schematic.",
    },
    {
        "key": "kerogen_organic_nanopore_storage_transport",
        "manuscript_type": "large_review",
        "status": "candidate",
        "title": "Kerogen and organic nanopore controls on gas storage and transport",
        "core_question": "How do kerogen type, maturity, pore geometry, water, and organic-inorganic interfaces control methane, CO2, and mixed-gas adsorption and diffusion?",
        "required_any": [["kerogen", "organic matter", "toc", "organic nanopore"]],
        "focus_terms": [
            "adsorption",
            "sorption",
            "diffusion",
            "transport",
            "methane",
            "co2",
            "h2",
            "water",
            "maturity",
            "pore",
            "nanopore",
            "interface",
            "shale",
            "organic",
        ],
        "target_journal_direction": "shale gas / organic geochemistry / nanopore transport review",
        "innovation_points": [
            "Centers kerogen and organic nanopores rather than treating them as background to clay/mineral effects.",
            "Links kerogen type, maturity, water, pore geometry, and mixed-gas competition.",
            "Can reuse some shale evidence while maintaining a distinct organic-matter thesis.",
        ],
        "figure_strategy": "Kerogen type/maturity map, organic nanopore mechanism schematic, gas competition panels.",
    },
    {
        "key": "hydrogen_subsurface_storage_competition",
        "manuscript_type": "large_review_or_focused_review",
        "status": "candidate",
        "title": "Hydrogen, methane, and carbon dioxide competition in subsurface nanoporous storage systems",
        "core_question": "What controls H2/CH4/CO2 competitive adsorption, diffusion, and storage security in shale, coal, and other nanoporous geological media?",
        "required_any": [["hydrogen", "h2", "underground hydrogen storage"]],
        "focus_terms": [
            "adsorption",
            "diffusion",
            "storage",
            "methane",
            "co2",
            "competition",
            "competitive adsorption",
            "cushion gas",
            "shale",
            "coal",
            "nanopore",
            "subsurface",
        ],
        "target_journal_direction": "hydrogen energy / underground storage review",
        "innovation_points": [
            "Moves beyond shale gas toward H2/CH4/CO2 competition in subsurface storage.",
            "Frames cushion gas, adsorption competition, diffusion barriers, and storage security as one problem.",
            "Has low overlap with the completed clay manuscript and strong recency.",
        ],
        "figure_strategy": "H2/CH4/CO2 competition schematic, cushion-gas comparison matrix, storage-security risk map.",
    },
    {
        "key": "coal_cbm_adsorption_displacement",
        "manuscript_type": "focused_review",
        "status": "candidate",
        "title": "Coal and coalbed methane adsorption-displacement under CO2, N2, water, and pressure-temperature controls",
        "core_question": "How do moisture, coal rank, pore structure, and injected gases control CH4 adsorption, diffusion, and displacement in coal systems?",
        "required_any": [["coal", "coalbed", "cbm"]],
        "focus_terms": [
            "methane",
            "co2",
            "n2",
            "water",
            "moisture",
            "adsorption",
            "desorption",
            "diffusion",
            "displacement",
            "recovery",
            "pressure",
            "temperature",
            "pore",
        ],
        "target_journal_direction": "coalbed methane / adsorption and displacement review",
        "innovation_points": [
            "Uses coal/CBM as a focused adsorption-displacement system distinct from shale.",
            "Connects moisture, pressure-temperature, gas affinity, pore structure, and CO2/N2 displacement.",
            "Likely stronger as a focused review than a flagship mega-review unless more coal papers are added.",
        ],
        "figure_strategy": "Coal displacement mechanism map, gas-affinity ranking table, moisture-depth boundary figure.",
    },
]


METHOD_CANDIDATE = {
    "key": "auto_review_traceable_ai_method",
    "manuscript_type": "method_or_software_paper",
    "status": "candidate",
    "title": "Traceable AI-assisted systematic review generation from PDF decomposition, evidence graphs, expert agents, and LaTeX/PDF production",
    "core_question": "Can Auto_review turn a folder of PDFs into traceable evidence atoms, paper-level syntheses, cross-paper relations, long manuscripts, expert review records, figures, and compiled PDFs without manual rewriting of AI output?",
    "target_journal_direction": "scientific software / AI-assisted literature review methods",
    "innovation_points": [
        "Presents traceability as the core answer to AI-generated review reliability.",
        "Demonstrates an end-to-end PDF-to-evidence-to-graph-to-manuscript-to-figures-to-PDF pipeline.",
        "Includes expert-agent review and deterministic gates instead of manual rewriting of AI output.",
    ],
    "figure_strategy": "Pipeline architecture, evidence provenance diagram, gate/expert workflow, case-study output matrix.",
}


# Gas names matched against material occurrence surface (lowercased) and
# against the canonical display_name from the element registry (lowercased).
GAS_NAMES: frozenset[str] = frozenset({
    "methane", "carbon dioxide", "hydrogen", "nitrogen", "water",
    "ch4", "co2", "h2", "n2", "h2o", "helium", "ethane", "propane",
})


def collect_paper_inputs(paper_dir: Path, card: dict) -> dict:
    """Read elements.json + legacy files for one paper; return a normalised inputs dict.

    Atoms-equivalent: elements with facet in {"finding","analysis"} and role=="used".
    Syntheses-equivalent: card summary.main_findings wrapped as claim dicts.
    Gas systems: used material occurrences whose surface or canonical display_name
                 (lowercased) matches GAS_NAMES.
    Falls back to empty structures when elements.json is absent (legacy papers).
    """
    elements_obj = read_json(paper_dir / "elements.json", {})
    occurrences: list[dict] = []
    if isinstance(elements_obj, dict):
        occurrences = elements_obj.get("occurrences") or []

    # atoms-equivalent: finding + analysis facets, used role only
    atoms: list[dict] = []
    for occ in occurrences:
        if occ.get("facet") in {"finding", "analysis"} and occ.get("role") == "used":
            atoms.append({
                "atom_type": occ.get("facet"),        # facet as atom_type
                "minimal_claim": occ.get("surface", ""),
                "quote": occ.get("quote", ""),
                "topic_tags": [],                      # elements have no topic_tags
            })

    # syntheses-equivalent: card summary.main_findings
    summary = card.get("summary") or {}
    main_findings: list[str] = summary.get("main_findings") or []
    syntheses: list[dict] = [
        {"claim": text, "synthesis_id": f"MF-{i:02d}", "synthesis_type": "main_finding"}
        for i, text in enumerate(main_findings)
    ]

    # gas systems: used material occurrences whose surface or canonical display_name matches GAS_NAMES
    gas_systems: list[str] = []
    seen_gas: set[str] = set()
    for occ in occurrences:
        if occ.get("facet") != "material" or occ.get("role") != "used":
            continue
        surface_lower = (occ.get("surface") or "").lower()
        # canonical display_name embedded in canonical_id as the slug after the last "/"
        canonical_id = occ.get("canonical_id") or ""
        display_lower = canonical_id.split("/")[-1].replace("-", " ").lower() if canonical_id else ""
        matched = (surface_lower in GAS_NAMES) or (display_lower in GAS_NAMES)
        if matched:
            label = (occ.get("surface") or "").strip()
            if label and label not in seen_gas:
                seen_gas.add(label)
                gas_systems.append(label)

    return {
        "atoms": atoms,
        "syntheses": syntheses,
        "gas_systems": gas_systems,
        "evidence_atoms_count": len(atoms),       # counts only finding+analysis from elements
        "syntheses_count": len(syntheses),         # = number of main_findings in card summary
        # Note: CSV columns keep names "evidence_atoms"/"paper_syntheses" for compatibility
    }


def read_json(path: Path, default=None):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(run_dir: Path) -> None:
    files = []
    for path in sorted(p for p in run_dir.rglob("*") if p.is_file() and p.name != "manifest.json"):
        files.append(
            {
                "path": str(path.relative_to(run_dir)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    write_json(run_dir / "manifest.json", {"manifest_version": "paper-portfolio-manifest-v1", "files": files})


def resolve_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def norm_text(value) -> str:
    text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
    replacements = {
        "\u2080": "0",
        "\u2081": "1",
        "\u2082": "2",
        "\u2083": "3",
        "\u2084": "4",
        "\u2085": "5",
        "\u2086": "6",
        "\u2087": "7",
        "\u2088": "8",
        "\u2089": "9",
        "\u207a": "+",
        "\u00b2": "2",
        "\u2013": "-",
        "\u2014": "-",
        "\u2011": "-",
        "\u00a0": " ",
        "â€“": "-",
        "â€”": "-",
        "â€‘": "-",
        "Â²": "2",
        "Ã…": "angstrom",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.lower()
    text = text.replace("carbon dioxide", "co2")
    text = text.replace("methane", "ch4 methane")
    return re.sub(r"\s+", " ", text)


def contains_any(text: str, terms: list[str]) -> bool:
    return any(norm_text(term) in text for term in terms)


def matched_terms(text: str, terms: list[str]) -> list[str]:
    return sorted({term for term in terms if norm_text(term) in text})


def flatten_card_text(card: dict, syntheses: list[dict], atoms: list[dict]) -> str:
    summary = card.get("summary") or {}
    classification = card.get("classification") or {}
    parts = [
        (card.get("paper") or {}).get("title", ""),
        (card.get("paper") or {}).get("paper_type", ""),
        summary,
        classification,
        [item.get("claim", "") for item in syntheses],
        [item.get("minimal_claim", "") for item in atoms],
        [item.get("topic_tags", []) for item in atoms],
    ]
    return norm_text(parts)


def paper_year(card: dict) -> int | None:
    value = str((card.get("paper") or {}).get("year") or "").strip()
    match = re.search(r"(19|20)\d{2}", value)
    return int(match.group(0)) if match else None


def list_figures(paper_dir: Path) -> list[Path]:
    fig_dir = paper_dir / "figures"
    if not fig_dir.exists():
        return []
    return sorted(p for p in fig_dir.glob("*") if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".svg"})


def load_papers(library_dir: Path) -> dict[str, dict]:
    papers = {}
    for paper_dir in sorted(library_dir.glob("S*")):
        if not paper_dir.is_dir():
            continue
        card = read_json(paper_dir / "literature_card.json", {})
        figures = list_figures(paper_dir)
        if not card:
            continue
        inputs = collect_paper_inputs(paper_dir, card)
        atoms = inputs["atoms"]
        syntheses = inputs["syntheses"]
        classification = card.get("classification") or {}
        papers[paper_dir.name] = {
            "paper_id": paper_dir.name,
            "dir": str(paper_dir),
            "title": (card.get("paper") or {}).get("title", ""),
            "doi": (card.get("paper") or {}).get("doi", ""),
            "year": paper_year(card),
            "paper_type": (card.get("paper") or {}).get("paper_type", ""),
            "research_objects": classification.get("research_objects") or [],
            "methods": classification.get("methods") or [],
            "domain_tags": classification.get("domain_tags") or [],
            # gas_systems derived from elements.json material occurrences (see collect_paper_inputs)
            "gas_systems": inputs["gas_systems"],
            "summary": card.get("summary") or {},
            "atoms": atoms,
            "syntheses": syntheses,
            "figures_count": len(figures),
            # evidence_atoms_count = finding+analysis elements (used only);
            # syntheses_count = main_findings from card summary.
            # Column names kept for CSV compatibility.
            "evidence_atoms_count": inputs["evidence_atoms_count"],
            "syntheses_count": inputs["syntheses_count"],
            "quantitative_atoms_count": sum(1 for atom in atoms if "quant" in str(atom.get("atom_type", "")).lower()),
            "text": flatten_card_text(card, syntheses, atoms),
        }
    return papers


def load_edges(connection_dir: Path) -> list[dict]:
    data = read_json(connection_dir / "edges.json", {}) or {}
    return data.get("edges") or []


def load_concept_index(connection_dir: Path) -> dict:
    data = read_json(connection_dir / "concept_index.json", {}) or {}
    return data.get("concepts") or {}


def accepted_run_from_latest(base: Path) -> Path | None:
    root = base / "sectioned_manuscripts"
    if not root.exists():
        return None
    candidates = []
    for run_dir in root.glob("sectioned_manuscript_*"):
        decision = read_json(run_dir / "final_decision.json", {}) or {}
        summary = read_json(run_dir / "sectioned_summary.json", {}) or {}
        if decision.get("gate_decision") == "internal_acceptance_gate" or summary.get("status") == "internal_acceptance_gate":
            candidates.append(run_dir)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: item.stat().st_mtime, reverse=True)[0]


def paper_ids_from_text(text: str) -> set[str]:
    return set(re.findall(r"\bS\d+\b", text))


def accepted_manuscript_papers(run_dir: Path | None) -> dict:
    if not run_dir:
        return {"run_dir": "", "paper_ids": []}
    paper_ids: set[str] = set()
    for name in ["draft_v01_repair01.md", "draft_v01.md", "final_draft_repair01.md", "final_draft.md"]:
        path = run_dir / name
        if path.exists():
            paper_ids.update(paper_ids_from_text(path.read_text(encoding="utf-8")))
    for name in ["claim_register_v01_repair01.json", "claim_register_v01.json", "final_claim_register.json", "brief.json", "final_brief.json"]:
        obj = read_json(run_dir / name, None)
        if obj is not None:
            paper_ids.update(paper_ids_from_text(json.dumps(obj, ensure_ascii=False)))
    return {"run_dir": str(run_dir), "paper_ids": sorted(paper_ids)}


def score_paper_for_candidate(paper: dict, candidate: dict) -> tuple[float, list[str]]:
    text = paper["text"]
    for required_group in candidate.get("required_any") or []:
        if not contains_any(text, required_group):
            return 0.0, []
    terms = candidate.get("focus_terms") or []
    found = matched_terms(text, terms)
    if not found:
        return 0.0, []
    title_text = norm_text(paper.get("title", ""))
    title_hits = matched_terms(title_text, terms)
    class_text = norm_text(
        {
            "research_objects": paper.get("research_objects", []),
            "methods": paper.get("methods", []),
            "domain_tags": paper.get("domain_tags", []),
            "gas_systems": paper.get("gas_systems", []),
        }
    )
    class_hits = matched_terms(class_text, terms)
    score = len(found) + 2.0 * len(title_hits) + 1.5 * len(class_hits)
    score += min(paper.get("syntheses_count", 0), 6) * 0.25
    score += min(paper.get("evidence_atoms_count", 0), 20) * 0.05
    return score, found


def select_topic_papers(papers: dict[str, dict], candidate: dict, max_papers: int) -> tuple[list[dict], dict[str, list[str]]]:
    scored = []
    terms_by_paper: dict[str, list[str]] = {}
    for paper in papers.values():
        score, found = score_paper_for_candidate(paper, candidate)
        if score <= 0:
            continue
        scored.append((score, paper))
        terms_by_paper[paper["paper_id"]] = found
    scored.sort(key=lambda item: (item[0], item[1].get("evidence_atoms_count", 0), item[1]["paper_id"]), reverse=True)
    return [paper for _, paper in scored[:max_papers]], terms_by_paper


def internal_edges(selected: set[str], edges: list[dict]) -> list[dict]:
    rows = [edge for edge in edges if edge.get("a") in selected and edge.get("b") in selected]
    priority = {"contradicts": 3, "complements": 2, "supports": 1}
    rows.sort(key=lambda item: (priority.get(item.get("relation"), 0), float(item.get("candidate_score") or 0)), reverse=True)
    return rows


def concept_support(selected: set[str], concept_index: dict, limit: int = 18) -> list[dict]:
    rows = []
    for concept, item in concept_index.items():
        central = set(item.get("central") or [])
        passing = {mention.get("paper") for mention in item.get("passing") or []}
        overlap = sorted((central | passing) & selected)
        if not overlap:
            continue
        rows.append(
            {
                "concept": concept,
                "paper_ids": overlap[:18],
                "n_overlap": len(overlap),
                "n_central": len(central & selected),
                "n_passing": len(passing & selected),
                "specific": bool(item.get("specific")),
                "gap_score": item.get("gap_score", 0),
                "facets": item.get("facets", []),
            }
        )
    rows.sort(key=lambda item: (item["n_overlap"], item["n_central"], item["specific"], item["gap_score"]), reverse=True)
    return rows[:limit]


def sample_claims(candidate: dict, selected_papers: list[dict], terms_by_paper: dict[str, list[str]], limit: int = 24) -> list[dict]:
    rows = []
    seen = set()
    focus_terms = candidate.get("focus_terms") or []
    for paper in selected_papers:
        pid = paper["paper_id"]
        paper_terms = terms_by_paper.get(pid, [])
        for synth in paper.get("syntheses") or []:
            claim = str(synth.get("claim") or "").strip()
            if not claim:
                continue
            matched = matched_terms(norm_text(claim), focus_terms) or paper_terms[:5]
            if not matched:
                continue
            key = (pid, claim)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "paper_id": pid,
                    "source": f"{pid}/paper_syntheses.json#{synth.get('synthesis_id', '')}",
                    "text": claim,
                    "matched_terms": matched[:8],
                    "supporting_evidence_atom_ids": synth.get("supporting_evidence_atom_ids") or [],
                }
            )
            if len(rows) >= limit:
                return rows
        for atom in paper.get("atoms") or []:
            claim = str(atom.get("minimal_claim") or atom.get("quote") or "").strip()
            if not claim:
                continue
            matched = matched_terms(norm_text({"claim": claim, "tags": atom.get("topic_tags", [])}), focus_terms)
            if not matched:
                continue
            key = (pid, claim)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "paper_id": pid,
                    "source": f"{pid}/evidence_atoms.json#{atom.get('evidence_atom_id', '')}",
                    "text": claim,
                    "matched_terms": matched[:8],
                    "page_start": atom.get("page_start"),
                    "page_end": atom.get("page_end"),
                }
            )
            if len(rows) >= limit:
                return rows
    return rows


def support_level(n_papers: int, n_atoms: int, n_syntheses: int, n_edges: int) -> str:
    if n_papers >= 45 and n_atoms >= 350 and n_syntheses >= 90 and n_edges >= 40:
        return "strong_12000_word_review"
    if n_papers >= 28 and n_atoms >= 180 and n_syntheses >= 50:
        return "borderline_or_focused_large_review"
    return "insufficient_for_12000_without_more_evidence"


def topic_metrics(
    candidate: dict,
    selected_papers: list[dict],
    terms_by_paper: dict[str, list[str]],
    edges: list[dict],
    concept_index: dict,
    accepted_papers: set[str],
) -> dict:
    selected_ids = {paper["paper_id"] for paper in selected_papers}
    topic_edges = internal_edges(selected_ids, edges)
    relation_counts = Counter(edge.get("relation") for edge in topic_edges)
    n_papers = len(selected_papers)
    n_atoms = sum(paper.get("evidence_atoms_count", 0) for paper in selected_papers)
    n_quant = sum(paper.get("quantitative_atoms_count", 0) for paper in selected_papers)
    n_syntheses = sum(paper.get("syntheses_count", 0) for paper in selected_papers)
    n_figures = sum(paper.get("figures_count", 0) for paper in selected_papers)
    methods = sorted({method for paper in selected_papers for method in paper.get("methods", [])})
    gases = sorted({gas for paper in selected_papers for gas in paper.get("gas_systems", [])})
    objects = sorted({obj for paper in selected_papers for obj in paper.get("research_objects", [])})
    years = [paper.get("year") for paper in selected_papers if paper.get("year")]
    recent = sum(1 for year in years if year >= 2024)
    overlap = selected_ids & accepted_papers
    overlap_ratio = len(overlap) / n_papers if n_papers else 0.0
    density = len(topic_edges) / (n_papers * (n_papers - 1) / 2) if n_papers > 1 else 0.0
    evidence_score = min(35, n_papers * 0.45 + n_atoms * 0.012 + n_syntheses * 0.035)
    relation_score = min(25, relation_counts.get("contradicts", 0) * 2.2 + relation_counts.get("complements", 0) * 0.45 + relation_counts.get("supports", 0) * 0.25)
    method_score = min(12, len(methods) * 0.8 + len(gases) * 0.8 + len(objects) * 0.25)
    figure_score = min(14, n_figures * 0.08)
    recency_score = min(8, recent * 0.25)
    overlap_penalty = 0 if candidate.get("status") == "already_generated_flagship" else min(24, overlap_ratio * 24)
    priority_score = round(evidence_score + relation_score + method_score + figure_score + recency_score - overlap_penalty, 2)
    top_papers = sorted(
        selected_papers,
        key=lambda paper: (len(terms_by_paper.get(paper["paper_id"], [])), paper.get("evidence_atoms_count", 0), paper.get("figures_count", 0)),
        reverse=True,
    )[:18]
    figure_potential = figure_potential_label(n_figures, n_quant, relation_counts, candidate.get("figure_strategy", ""))
    next_generation_readiness = readiness_label(
        support_level(n_papers, n_atoms, n_syntheses, len(topic_edges)),
        overlap_risk(overlap_ratio, candidate.get("status", "candidate")),
        len(topic_edges),
    )
    return {
        "key": candidate["key"],
        "manuscript_type": candidate["manuscript_type"],
        "status": candidate.get("status", "candidate"),
        "title": candidate["title"],
        "core_question": candidate["core_question"],
        "target_journal_direction": candidate["target_journal_direction"],
        "innovation_points": candidate.get("innovation_points", []),
        "figure_strategy": candidate.get("figure_strategy", ""),
        "figure_potential": figure_potential,
        "next_generation_readiness": next_generation_readiness,
        "support_level": support_level(n_papers, n_atoms, n_syntheses, len(topic_edges)),
        "priority_score": priority_score,
        "scores": {
            "evidence_score": round(evidence_score, 2),
            "relation_score": round(relation_score, 2),
            "method_diversity_score": round(method_score, 2),
            "figure_score": round(figure_score, 2),
            "recency_score": round(recency_score, 2),
            "overlap_penalty": round(overlap_penalty, 2),
        },
        "evidence_volume": {
            "papers": n_papers,
            "evidence_atoms": n_atoms,
            "quantitative_atoms": n_quant,
            "paper_syntheses": n_syntheses,
            "source_figures": n_figures,
            "recent_papers_2024_plus": recent,
            "year_range": [min(years), max(years)] if years else [],
        },
        "selected_paper_ids": sorted(selected_ids),
        "cross_paper_relations": {
            "internal_edges": len(topic_edges),
            "edge_density": round(density, 4),
            "supports": relation_counts.get("supports", 0),
            "complements": relation_counts.get("complements", 0),
            "contradicts": relation_counts.get("contradicts", 0),
            "top_edges": topic_edges[:16],
        },
        "overlap_with_completed_manuscript": {
            "overlap_papers": sorted(overlap),
            "overlap_count": len(overlap),
            "overlap_ratio": round(overlap_ratio, 3),
            "risk": overlap_risk(overlap_ratio, candidate.get("status", "candidate")),
        },
        "diversity": {
            "methods": methods[:40],
            "gas_systems": gases[:40],
            "research_objects": objects[:50],
        },
        "traceable_concepts": concept_support(selected_ids, concept_index),
        "representative_papers": [
            {
                "paper_id": paper["paper_id"],
                "title": paper.get("title", ""),
                "year": paper.get("year"),
                "paper_type": paper.get("paper_type", ""),
                "matched_terms": terms_by_paper.get(paper["paper_id"], [])[:12],
                "evidence_atoms": paper.get("evidence_atoms_count", 0),
                "paper_syntheses": paper.get("syntheses_count", 0),
                "source_figures": paper.get("figures_count", 0),
                "source_path": str(ROOT / "library" / paper["paper_id"]),
            }
            for paper in top_papers
        ],
        "representative_claims": sample_claims(candidate, top_papers, terms_by_paper),
    }


def figure_potential_label(n_figures: int, n_quant: int, relation_counts: Counter, strategy: str) -> dict:
    score = min(100, n_figures * 0.035 + n_quant * 0.05 + relation_counts.get("contradicts", 0) * 2 + relation_counts.get("complements", 0) * 0.12)
    if score >= 80:
        level = "high_multi_panel_review_potential"
    elif score >= 45:
        level = "moderate_needs_curated_redrawing"
    else:
        level = "limited_needs_more_visual_sources"
    return {
        "level": level,
        "score": round(score, 2),
        "source_figures": n_figures,
        "quantitative_atoms": n_quant,
        "suggested_strategy": strategy,
    }


def readiness_label(level: str, overlap: str, n_edges: int) -> str:
    if level == "insufficient_for_12000_without_more_evidence":
        return "do_not_generate_full_manuscript_yet"
    if overlap == "high_overlap_reframe_or_delay":
        return "delay_until_distinct_thesis_is_locked"
    if n_edges < 60:
        return "generate_focused_review_or_expand_edges_first"
    return "ready_for_sectioned_manuscript_generation"


def overlap_risk(ratio: float, status: str) -> str:
    if status == "already_generated_flagship":
        return "completed_reference_manuscript"
    if ratio >= 0.65:
        return "high_overlap_reframe_or_delay"
    if ratio >= 0.35:
        return "moderate_overlap_requires_distinct_thesis"
    return "low_overlap"


def method_paper_metrics(papers: dict, edges: list[dict], accepted_info: dict, reports_dir: Path) -> dict:
    script_files = sorted(p for p in (ROOT / "scripts").rglob("*.py") if "__pycache__" not in str(p))
    prompt_files = sorted((ROOT / "prompts").rglob("*.md")) if (ROOT / "prompts").exists() else []
    generated_evidence = sum(paper.get("evidence_atoms_count", 0) for paper in papers.values())
    generated_syntheses = sum(paper.get("syntheses_count", 0) for paper in papers.values())
    figures = list(reports_dir.glob("figures/*/figure_plan_validation.json"))
    exports = list(reports_dir.glob("manuscript_exports_with_figures/*/*.pdf"))
    stages = {
        "pdf_ingest_and_package": bool((ROOT / "scripts" / "run_pipeline.py").exists()),
        # Probe elements.json (new pipeline); fall back to legacy evidence_atoms.json.
        "evidence_atoms": any(
            (ROOT / "library" / pid / "elements.json").exists()
            or (ROOT / "library" / pid / "evidence_atoms.json").exists()
            for pid in papers
        ),
        "paper_syntheses": any(
            (ROOT / "library" / pid / "elements.json").exists()
            or (ROOT / "library" / pid / "paper_syntheses.json").exists()
            for pid in papers
        ),
        "connection_graph": (reports_dir / "connection" / "edges.json").exists(),
        "long_manuscript_writer": (ROOT / "scripts" / "write" / "run_sectioned_manuscript.py").exists(),
        "expert_review": bool(accepted_info.get("run_dir")),
        "figure_pipeline": bool(figures),
        "latex_pdf_export": bool(exports),
    }
    completed_stages = sum(1 for value in stages.values() if value)
    priority_score = round(40 + completed_stages * 5 + min(20, len(script_files) * 0.25) + min(15, generated_evidence / 300), 2)
    return {
        **METHOD_CANDIDATE,
        "support_level": "method_paper_supported_by_project_artifacts" if completed_stages >= 6 else "needs_more_system_validation",
        "figure_potential": {
            "level": "high_workflow_figure_potential" if completed_stages >= 6 else "moderate_workflow_figure_potential",
            "score": min(100, completed_stages * 10 + len(script_files) * 0.25),
            "suggested_strategy": METHOD_CANDIDATE["figure_strategy"],
        },
        "next_generation_readiness": "ready_for_method_manuscript_generation" if completed_stages >= 6 else "needs_more_system_validation",
        "priority_score": priority_score,
        "scores": {
            "pipeline_stage_score": completed_stages,
            "script_surface_score": round(min(20, len(script_files) * 0.25), 2),
            "artifact_score": round(min(15, generated_evidence / 300), 2),
            "overlap_penalty": 0,
        },
        "evidence_volume": {
            "library_papers_with_records": len(papers),
            "evidence_atoms": generated_evidence,
            "paper_syntheses": generated_syntheses,
            "connection_edges": len(edges),
            "script_files": len(script_files),
            "prompt_files": len(prompt_files),
            "accepted_manuscript_run": accepted_info.get("run_dir", ""),
            "compiled_pdfs_with_figures": len(exports),
        },
        "system_stages": stages,
        "overlap_with_completed_manuscript": {
            "overlap_count": 0,
            "overlap_ratio": 0.0,
            "risk": "different_output_type_method_paper",
        },
        "traceable_artifacts": [
            str(ROOT / "scripts" / "run_pipeline.py"),
            str(ROOT / "scripts" / "connect" / "ai_build_edges.py"),
            str(ROOT / "scripts" / "write" / "run_sectioned_manuscript.py"),
            str(ROOT / "scripts" / "figures" / "export_manuscript_with_figures.py"),
            str(reports_dir / "connection" / "edges.json"),
            accepted_info.get("run_dir", ""),
        ],
        "representative_papers": [],
        "representative_claims": [],
        "cross_paper_relations": {
            "internal_edges": len(edges),
            "supports": sum(1 for edge in edges if edge.get("relation") == "supports"),
            "complements": sum(1 for edge in edges if edge.get("relation") == "complements"),
            "contradicts": sum(1 for edge in edges if edge.get("relation") == "contradicts"),
        },
    }


def portfolio_recommendations(rows: list[dict], max_count: int) -> list[dict]:
    candidates = [
        row
        for row in rows
        if row.get("status") != "already_generated_flagship"
        and row.get("support_level") != "insufficient_for_12000_without_more_evidence"
    ]
    candidates.sort(key=lambda item: item.get("priority_score", 0), reverse=True)
    return [
        {
            "rank": index,
            "key": row["key"],
            "title": row["title"],
            "manuscript_type": row["manuscript_type"],
            "priority_score": row["priority_score"],
            "support_level": row["support_level"],
            "reason": recommendation_reason(row),
        }
        for index, row in enumerate(candidates[:max_count], start=1)
    ]


def recommendation_reason(row: dict) -> str:
    ev = row.get("evidence_volume", {})
    rel = row.get("cross_paper_relations", {})
    risk = (row.get("overlap_with_completed_manuscript") or {}).get("risk", "")
    if row.get("manuscript_type") == "method_or_software_paper":
        return "Distinct from the shale science papers and supported by pipeline artifacts, traces, expert review outputs, figure generation, and compiled PDFs."
    return (
        f"Evidence volume is {ev.get('papers', 0)} papers / {ev.get('evidence_atoms', 0)} atoms, "
        f"with {rel.get('contradicts', 0)} contradiction edges and {rel.get('complements', 0)} complement edges; "
        f"overlap risk is {risk}."
    )


def candidate_overlap_matrix(rows: list[dict]) -> list[dict]:
    paper_sets = {}
    for row in rows:
        ids = set(row.get("selected_paper_ids") or [])
        if not ids:
            ids = {
                paper.get("paper_id")
                for paper in row.get("representative_papers") or []
                if paper.get("paper_id")
            }
        overlap_ids = set((row.get("overlap_with_completed_manuscript") or {}).get("overlap_papers") or [])
        ids.update(overlap_ids)
        for claim in row.get("representative_claims") or []:
            if claim.get("paper_id"):
                ids.add(claim.get("paper_id"))
        paper_sets[row["key"]] = ids
    matrix = []
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            a_set = paper_sets.get(a["key"], set())
            b_set = paper_sets.get(b["key"], set())
            if not a_set or not b_set:
                jaccard = 0.0
                shared = []
            else:
                shared_set = a_set & b_set
                union = a_set | b_set
                jaccard = len(shared_set) / len(union) if union else 0.0
                shared = sorted(shared_set)
            matrix.append(
                {
                    "a": a["key"],
                    "b": b["key"],
                    "shared_representative_papers": shared,
                    "shared_count": len(shared),
                    "representative_jaccard": round(jaccard, 3),
                    "risk": pair_overlap_risk(jaccard),
                }
            )
    matrix.sort(key=lambda item: (item["representative_jaccard"], item["shared_count"]), reverse=True)
    return matrix


def pair_overlap_risk(jaccard: float) -> str:
    if jaccard >= 0.45:
        return "high_pair_overlap"
    if jaccard >= 0.25:
        return "moderate_pair_overlap"
    return "low_pair_overlap"


def attach_candidate_overlap(rows: list[dict], overlap_rows: list[dict]) -> None:
    by_key = {row["key"]: [] for row in rows}
    for item in overlap_rows:
        by_key.setdefault(item["a"], []).append(item)
        by_key.setdefault(item["b"], []).append(item)
    for row in rows:
        related = sorted(
            by_key.get(row["key"], []),
            key=lambda item: (item["representative_jaccard"], item["shared_count"]),
            reverse=True,
        )
        row["candidate_overlap_risks"] = related[:5]


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "rank",
        "key",
        "manuscript_type",
        "status",
        "support_level",
        "priority_score",
        "title",
        "core_question",
        "papers",
        "evidence_atoms",
        "paper_syntheses",
        "source_figures",
        "internal_edges",
        "supports",
        "complements",
        "contradicts",
        "overlap_ratio",
        "overlap_risk",
        "figure_potential",
        "next_generation_readiness",
        "innovation_points",
        "target_journal_direction",
    ]
    ranked = sorted(rows, key=lambda item: item.get("priority_score", 0), reverse=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(ranked, start=1):
            ev = row.get("evidence_volume", {})
            rel = row.get("cross_paper_relations", {})
            overlap = row.get("overlap_with_completed_manuscript", {})
            writer.writerow(
                {
                    "rank": index,
                    "key": row.get("key"),
                    "manuscript_type": row.get("manuscript_type"),
                    "status": row.get("status"),
                    "support_level": row.get("support_level"),
                    "priority_score": row.get("priority_score"),
                    "title": row.get("title"),
                    "core_question": row.get("core_question"),
                    "papers": ev.get("papers", ev.get("library_papers_with_records", "")),
                    "evidence_atoms": ev.get("evidence_atoms", ""),
                    "paper_syntheses": ev.get("paper_syntheses", ""),
                    "source_figures": ev.get("source_figures", ""),
                    "internal_edges": rel.get("internal_edges", ""),
                    "supports": rel.get("supports", ""),
                    "complements": rel.get("complements", ""),
                    "contradicts": rel.get("contradicts", ""),
                    "overlap_ratio": overlap.get("overlap_ratio", ""),
                    "overlap_risk": overlap.get("risk", ""),
                    "figure_potential": (row.get("figure_potential") or {}).get("level", ""),
                    "next_generation_readiness": row.get("next_generation_readiness", ""),
                    "innovation_points": " | ".join(row.get("innovation_points") or []),
                    "target_journal_direction": row.get("target_journal_direction"),
                }
            )


def md_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    header = rows[0]
    out = ["| " + " | ".join(header) + " |", "| " + " | ".join(["---"] * len(header)) + " |"]
    for row in rows[1:]:
        out.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(out)


def write_report(path: Path, matrix: dict) -> None:
    rows = sorted(matrix["portfolio_matrix"], key=lambda item: item.get("priority_score", 0), reverse=True)
    table = [["Rank", "Key", "Type", "Support", "Score", "Papers", "Atoms", "Edges", "Contr.", "Overlap"]]
    for index, row in enumerate(rows, start=1):
        ev = row.get("evidence_volume", {})
        rel = row.get("cross_paper_relations", {})
        overlap = row.get("overlap_with_completed_manuscript", {})
        table.append(
            [
                str(index),
                row["key"],
                row["manuscript_type"],
                row["support_level"],
                str(row["priority_score"]),
                str(ev.get("papers", ev.get("library_papers_with_records", ""))),
                str(ev.get("evidence_atoms", "")),
                str(rel.get("internal_edges", "")),
                str(rel.get("contradicts", "")),
                str(overlap.get("overlap_ratio", "")),
            ]
        )
    lines = [
        "# Auto_review Paper Portfolio Matrix",
        "",
        f"- Created: {matrix['created_at']}",
        f"- Library papers evaluated: {matrix['source_summary']['library_papers_evaluated']}",
        f"- Connection edges used: {matrix['source_summary']['connection_edges_used']}",
        f"- Accepted manuscript reference: `{matrix['accepted_manuscript']['run_dir']}`",
        "",
        "## Ranked Matrix",
        "",
        md_table(table),
        "",
        "## Recommended Next Manuscripts",
        "",
    ]
    for rec in matrix["recommended_next_3_to_5"]:
        lines.extend(
            [
                f"### {rec['rank']}. {rec['title']}",
                "",
                f"- Key: `{rec['key']}`",
                f"- Type: {rec['manuscript_type']}",
                f"- Priority score: {rec['priority_score']}",
                f"- Support: {rec['support_level']}",
                f"- Reason: {rec['reason']}",
                "",
            ]
        )
    lines.extend(["## Candidate Details", ""])
    for row in rows:
        ev = row.get("evidence_volume", {})
        rel = row.get("cross_paper_relations", {})
        overlap = row.get("overlap_with_completed_manuscript", {})
        lines.extend(
            [
                f"### {row['title']}",
                "",
                f"- Key: `{row['key']}`",
                f"- Core question: {row['core_question']}",
                f"- Target journal direction: {row['target_journal_direction']}",
                f"- Next generation readiness: {row.get('next_generation_readiness', '')}",
                f"- Figure potential: {(row.get('figure_potential') or {}).get('level', '')} ({(row.get('figure_potential') or {}).get('score', '')})",
                f"- Evidence: {ev}",
                f"- Relations: internal={rel.get('internal_edges')}, supports={rel.get('supports')}, complements={rel.get('complements')}, contradicts={rel.get('contradicts')}",
                f"- Overlap risk: {overlap.get('risk')} ({overlap.get('overlap_ratio', '')})",
                f"- Figure strategy: {row.get('figure_strategy', '')}",
                "",
                "Innovation points:",
            ]
        )
        for point in row.get("innovation_points") or []:
            lines.append(f"- {point}")
        lines.extend(
            [
                "",
                "Closest candidate overlaps:",
            ]
        )
        for item in (row.get("candidate_overlap_risks") or [])[:3]:
            other = item["b"] if item["a"] == row["key"] else item["a"]
            lines.append(
                f"- `{other}`: {item['risk']} (Jaccard={item['representative_jaccard']}, shared={item['shared_count']})"
            )
        lines.extend(
            [
                "",
                "Representative papers:",
            ]
        )
        for paper in (row.get("representative_papers") or [])[:6]:
            lines.append(f"- `{paper['paper_id']}` {paper.get('year') or ''}: {paper.get('title', '')}")
        if row.get("representative_claims"):
            lines.append("")
            lines.append("Representative traceable claims:")
            for claim in row["representative_claims"][:5]:
                lines.append(f"- `{claim['source']}`: {claim['text']}")
        if row.get("traceable_artifacts"):
            lines.append("")
            lines.append("Traceable artifacts:")
            for artifact in row["traceable_artifacts"]:
                if artifact:
                    lines.append(f"- `{artifact}`")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def build_portfolio(args) -> Path:
    library_dir = resolve_path(args.library_dir) or ROOT / "library"
    reports_dir = resolve_path(args.reports_dir) or ROOT / "reports"
    connection_dir = resolve_path(args.connection_dir) or reports_dir / "connection"
    accepted_run = resolve_path(args.accepted_run_dir) or accepted_run_from_latest(reports_dir)
    out_base = resolve_path(args.out_dir) or reports_dir / "portfolio"
    run_id = f"paper_portfolio_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_{uuid4().hex[:8]}"
    run_dir = out_base / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    papers = load_papers(library_dir)
    edges = load_edges(connection_dir)
    concept_index = load_concept_index(connection_dir)
    accepted = accepted_manuscript_papers(accepted_run)
    accepted_set = set(accepted.get("paper_ids") or [])

    matrix_rows = []
    for candidate in SCIENTIFIC_CANDIDATES:
        selected, terms_by_paper = select_topic_papers(papers, candidate, args.max_papers_per_candidate)
        row = topic_metrics(candidate, selected, terms_by_paper, edges, concept_index, accepted_set)
        matrix_rows.append(row)
    matrix_rows.append(method_paper_metrics(papers, edges, accepted, reports_dir))
    matrix_rows.sort(key=lambda item: item.get("priority_score", 0), reverse=True)
    for rank, row in enumerate(matrix_rows, start=1):
        row["rank"] = rank
    overlap_rows = candidate_overlap_matrix(matrix_rows)
    attach_candidate_overlap(matrix_rows, overlap_rows)

    matrix = {
        "portfolio_version": "paper-portfolio-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "source_summary": {
            "library_dir": str(library_dir),
            "library_papers_evaluated": len(papers),
            "connection_dir": str(connection_dir),
            "connection_edges_used": len(edges),
            "concept_index_path": str(connection_dir / "concept_index.json"),
        },
        "accepted_manuscript": accepted,
        "scoring_policy": {
            "support_strong_threshold": ">=45 papers, >=350 evidence atoms, >=90 paper syntheses, >=40 internal relation edges",
            "overlap_risk_high": ">=0.65 overlap with completed manuscript paper ids",
            "priority_score": "evidence + relation + diversity + figures + recency - overlap penalty",
            "traceability": "Every scientific candidate includes source paper ids, representative claims, local paths, and relation edges.",
        },
        "portfolio_matrix": matrix_rows,
        "candidate_overlap_matrix": overlap_rows,
        "recommended_next_3_to_5": portfolio_recommendations(matrix_rows, args.recommendations),
    }

    write_json(run_dir / "paper_portfolio_matrix.json", matrix)
    write_csv(run_dir / "paper_portfolio_matrix.csv", matrix_rows)
    write_report(run_dir / "paper_portfolio_report.md", matrix)
    write_json(
        run_dir / "run_config.json",
        {
            "library_dir": str(library_dir),
            "reports_dir": str(reports_dir),
            "connection_dir": str(connection_dir),
            "accepted_run_dir": str(accepted_run) if accepted_run else "",
            "max_papers_per_candidate": args.max_papers_per_candidate,
            "recommendations": args.recommendations,
        },
    )
    write_manifest(run_dir)
    return run_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a traceable Auto_review paper portfolio matrix.")
    parser.add_argument("--library-dir", default=str(ROOT / "library"))
    parser.add_argument("--reports-dir", default=str(ROOT / "reports"))
    parser.add_argument("--connection-dir", default=str(ROOT / "reports" / "connection"))
    parser.add_argument("--accepted-run-dir", default=None)
    parser.add_argument("--out-dir", default=str(ROOT / "reports" / "portfolio"))
    parser.add_argument("--max-papers-per-candidate", type=int, default=120)
    parser.add_argument("--recommendations", type=int, default=5)
    args = parser.parse_args()
    run_dir = build_portfolio(args)
    print(f"Paper portfolio matrix: {run_dir / 'paper_portfolio_matrix.json'}")
    print(f"Paper portfolio report: {run_dir / 'paper_portfolio_report.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
