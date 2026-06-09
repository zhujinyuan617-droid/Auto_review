import json
from pathlib import Path

from autoreview_app.writing.ideation import load_angles, propose_candidate_angles

EDGES = [
    {"a": "S1", "b": "S2", "relation": "contradicts", "shared": {"topic": ["uptake"]}, "rationale": "disagree on uptake"},
    {"a": "S1", "b": "S3", "relation": "complements", "shared": {}, "rationale": "builds on"},
]
CIDX = {
    "methane uptake": {
        "n_central": 2, "n_passing": 6, "central": ["S1", "S2"],
        "passing": [{"paper": "S3"}], "gap_score": 0.9, "specific": True,
    },
}


def test_candidates_from_graph():
    out = propose_candidate_angles(EDGES, CIDX)
    assert len(out["tension"]) == 1
    assert out["tension"][0]["a"] == "S1"
    assert out["tension"][0]["why"] == "disagree on uptake"
    assert [g["concept"] for g in out["gaps"]] == ["methane uptake"]
    assert [s["concept"] for s in out["synthesis"]] == ["methane uptake"]


def test_load_angles_reads_files(tmp_path: Path):
    edges_path = tmp_path / "edges.json"
    edges_path.write_text(json.dumps({"edges": EDGES}), encoding="utf-8")
    cidx_path = tmp_path / "concept_index.json"
    cidx_path.write_text(json.dumps(CIDX), encoding="utf-8")

    out = load_angles(edges_path, cidx_path)
    assert len(out["tension"]) == 1
    assert out["gaps"][0]["concept"] == "methane uptake"


def test_load_angles_missing_files_empty(tmp_path: Path):
    out = load_angles(tmp_path / "nope.json", tmp_path / "nada.json")
    assert out == {"tension": [], "gaps": [], "synthesis": []}


def test_empty_angles_is_independent_copy(tmp_path: Path):
    # Mutating one empty result must not poison the next call.
    a = load_angles(tmp_path / "x.json", tmp_path / "y.json")
    a["tension"].append("sentinel")
    b = load_angles(tmp_path / "x.json", tmp_path / "y.json")
    assert b == {"tension": [], "gaps": [], "synthesis": []}


def test_malformed_files_degrade_to_empty(tmp_path: Path):
    edges_path = tmp_path / "edges.json"
    edges_path.write_text("not json", encoding="utf-8")
    cidx_path = tmp_path / "concept_index.json"
    cidx_path.write_text("[1, 2, 3]", encoding="utf-8")  # valid json, wrong type
    assert load_angles(edges_path, cidx_path) == {"tension": [], "gaps": [], "synthesis": []}
