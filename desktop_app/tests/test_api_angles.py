import json
from pathlib import Path

from fastapi.testclient import TestClient

from autoreview_app.api import create_app
from autoreview_app.config import AppConfig

EDGES = [{"a": "S1", "b": "S2", "relation": "contradicts", "shared": {}, "rationale": "disagree"}]
CIDX = {"uptake": {"n_central": 2, "n_passing": 6, "central": ["S1", "S2"], "passing": [], "gap_score": 0.5, "specific": True}}


def test_angles_endpoint(tmp_path: Path):
    edges_path = tmp_path / "edges.json"
    edges_path.write_text(json.dumps({"edges": EDGES}), encoding="utf-8")
    cidx_path = tmp_path / "concept_index.json"
    cidx_path.write_text(json.dumps(CIDX), encoding="utf-8")

    config = AppConfig(library_dir=tmp_path / "library", edges_path=edges_path, concept_index_path=cidx_path)
    resp = TestClient(create_app(config)).get("/writing/angles")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tension"]) == 1
    assert body["gaps"][0]["concept"] == "uptake"


def test_angles_endpoint_empty_when_unconfigured(tmp_path: Path):
    config = AppConfig(library_dir=tmp_path / "library")  # no edges/concept paths
    resp = TestClient(create_app(config)).get("/writing/angles")
    assert resp.json() == {"tension": [], "gaps": [], "synthesis": []}
