import json
from pathlib import Path

from autoreview_app.network.edges import load_edges


def test_missing_file_returns_empty_graph(tmp_path: Path):
    graph = load_edges(tmp_path / "nope.json")
    assert graph == {"edges": [], "relation_counts": {}, "n_edges": 0}


def test_loads_edges_and_counts(tmp_path: Path):
    path = tmp_path / "edges.json"
    path.write_text(json.dumps({
        "relation_counts": {"supports": 1, "contradicts": 1},
        "edges": [
            {"a": "S1", "b": "S2", "relation": "supports", "rationale": "x"},
            {"a": "S2", "b": "S3", "relation": "contradicts", "rationale": "y"},
        ],
    }), encoding="utf-8")

    graph = load_edges(path)
    assert graph["n_edges"] == 2
    assert graph["relation_counts"] == {"supports": 1, "contradicts": 1}
    assert graph["edges"][0]["a"] == "S1"


def test_malformed_file_returns_empty_graph(tmp_path: Path):
    path = tmp_path / "edges.json"
    path.write_text("not json", encoding="utf-8")
    assert load_edges(path) == {"edges": [], "relation_counts": {}, "n_edges": 0}
